"""Read-only contracts for the live trading cockpit.

The live cockpit is deliberately fail-closed: mock data is labelled as
mock and never exposed as a live quote, while real providers must return
validated candles before the cockpit can use them.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from app.api.routes.health import health_check
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.risk_engine.risk_engine import evaluate_risk
from app.risk_engine.risk_models import AccountState, RiskLimitsConfig
from app.core.config import get_settings
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles

router = APIRouter(prefix="/live", tags=["live"])

INSTRUMENTS = ("EUR/USD", "GBP/USD", "XAU/USD")
TIMEFRAMES = ("m5", "m15", "h1", "h4", "d1")
_TIMEFRAME_DELTAS = {"m5": timedelta(minutes=5), "m15": timedelta(minutes=15), "h1": timedelta(hours=1), "h4": timedelta(hours=4), "d1": timedelta(days=1)}

def _completed_candles(candles, timeframe: str):
    now = datetime.now(timezone.utc)
    delta = _TIMEFRAME_DELTAS[timeframe]
    return [c for c in candles if c.timestamp + delta <= now]


def _candle_payload(candle) -> dict:
    return {
        "timestamp": candle.timestamp.isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


@router.get("/overview")
async def live_overview(
    instrument: str = Query("EUR/USD"),
    timeframe: str = Query("h1"),
) -> dict:
    settings = get_settings()
    health = await health_check()
    selected = instrument if instrument in INSTRUMENTS else "EUR/USD"
    selected_timeframe = timeframe.lower() if timeframe.lower() in TIMEFRAMES else "h1"
    provider = settings.market_data_provider
    data_status = health["market_data"]
    decision = "NO_TRADE"
    reason = (
        "Live market data is not verified, so Tembo fails closed instead of "
        "inventing an entry."
    )
    return {
        "mode": "MT5_DEMO_READY" if settings.mt5_bridge_url else "PREPARING",
        "mt5": {
            "status": (
                "configured"
                if settings.mt5_bridge_url and settings.mt5_bridge_token
                else "not_connected"
            ),
            "message": (
                "Bridge configuration exists; terminal connectivity will be "
                "verified when the bridge is deployed."
                if settings.mt5_bridge_url
                else "Waiting for the MT5 bridge URL and token."
            ),
        },
        "execution": {
            "enabled": bool(settings.enable_live_execution),
            "note": (
                "Execution remains disabled until MT5 demo connectivity and "
                "safety tests are completed."
            ),
        },
        "market_data": {"provider": provider, "status": data_status},
        "context": {
            "news": health["news_service"],
            "calendar": (
                "configured"
                if settings.economic_calendar_provider != "mock"
                else "mock"
            ),
        },
        "instruments": [
            {
                "instrument": symbol,
                "timeframe": selected_timeframe,
                "provider": provider,
                "data_status": data_status,
                "current_price": None,
                "last_update": None,
                "decision": decision,
                "reason": reason,
            }
            for symbol in INSTRUMENTS
        ],
        "trade_plan": {
            "instrument": selected,
            "decision": decision,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "reason": reason,
        },
    }


@router.get("/market")
async def live_market(
    instrument: str = Query("EUR/USD"),
    timeframe: str = Query("h1"),
    limit: int = Query(120, ge=20, le=500),
) -> dict:
    """Return chart-ready quote/candle data without fabricating mock prices."""

    if instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Must be one of {INSTRUMENTS}.",
        )

    selected_timeframe = timeframe.lower()
    if selected_timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid timeframe {timeframe!r}. "
                f"Must be one of {TIMEFRAMES}."
            ),
        )

    settings = get_settings()

    if settings.market_data_provider == "mock":
        return {
            "instrument": instrument,
            "timeframe": selected_timeframe,
            "provider": "mock",
            "status": "mock",
            "current_price": None,
            "last_update": None,
            "candles": [],
            "data_quality": {
                "is_clean": False,
                "ohlc_violations": 0,
                "duplicate_timestamps": 0,
                "unexpected_gaps": 0,
            },
            "message": "Mock market data is intentionally not displayed as a live quote.",
        }

    try:
        provider = get_market_data_provider(settings.market_data_provider)
        current_price = await provider.get_current_price(instrument)
        candles = await provider.get_candles(
            instrument, selected_timeframe, limit=limit
        )
        candles = normalize_candles(candles)
        validation = validate_candles(candles, timeframe=selected_timeframe)
        metadata = await provider.get_instrument_metadata(instrument)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Live market data is unavailable: {exc}",
        ) from exc

    if not candles:
        raise HTTPException(
            status_code=503,
            detail="Live provider returned no completed candles.",
        )

    if not validation.is_clean:
        raise HTTPException(
            status_code=503,
            detail="Live provider returned invalid candle data; Tembo refused to display it.",
        )

    return {
        "instrument": instrument,
        "timeframe": selected_timeframe,
        "provider": settings.market_data_provider,
        "status": "available",
        "current_price": current_price,
        "last_update": candles[-1].timestamp.isoformat(),
        "instrument_metadata": {
            "symbol": metadata.symbol,
            "display_name": metadata.display_name,
            "pip_size": metadata.pip_size,
            "asset_class": metadata.asset_class,
        },
        "candles": [_candle_payload(candle) for candle in candles],
        "data_quality": {
            "is_clean": validation.is_clean,
            "ohlc_violations": len(validation.ohlc_violations),
            "duplicate_timestamps": len(validation.duplicate_timestamps),
            "unexpected_gaps": len(validation.unexpected_gaps),
        },
        "message": "Live provider data verified and normalized.",
    }


@router.get("/analysis")
async def live_analysis(
    instrument: str = Query("EUR/USD"),
    timeframe: str = Query("h1"),
) -> dict:
    """Analyze verified completed candles; never returns a trade direction."""
    if instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Must be one of {INSTRUMENTS}.",
        )

    selected_timeframe = timeframe.lower()
    if selected_timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe {timeframe!r}. Must be one of {TIMEFRAMES}.",
        )

    settings = get_settings()
    if settings.market_data_provider == "mock":
        return {
            "instrument": instrument,
            "timeframe": selected_timeframe,
            "provider": "mock",
            "status": "waiting",
            "message": "Technical analysis is waiting for verified live candles.",
            "analysis": None,
        }

    try:
        provider = get_market_data_provider(settings.market_data_provider)
        candles = await provider.get_candles(
            instrument, selected_timeframe, limit=200
        )
        candles = normalize_candles(candles)
        validation = validate_candles(candles, timeframe=selected_timeframe)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Live analysis data is unavailable: {exc}",
        ) from exc

    if not candles or not validation.is_clean:
        raise HTTPException(
            status_code=503,
            detail="Live analysis refused unverified candle data.",
        )

    from app.live_engine.analysis import analyze_candles

    result = analyze_candles(candles)
    return {
        "instrument": instrument,
        "timeframe": selected_timeframe,
        "provider": settings.market_data_provider,
        "status": result["status"],
        "message": (
            "Deterministic technical analysis of verified completed candles. "
            "This endpoint does not produce BUY/SELL decisions."
        ),
        "data_quality": {
            "is_clean": validation.is_clean,
            "ohlc_violations": len(validation.ohlc_violations),
            "duplicate_timestamps": len(validation.duplicate_timestamps),
            "unexpected_gaps": len(validation.unexpected_gaps),
        },
        "analysis": result,
    }


@router.get("/analysis/multi-timeframe")
async def live_multi_timeframe_analysis(
    instrument: str = Query("EUR/USD"),
) -> dict:
    """Summarize the same deterministic analysis across all cockpit timeframes."""
    if instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Must be one of {INSTRUMENTS}.",
        )

    settings = get_settings()
    if settings.market_data_provider == "mock":
        return {
            "instrument": instrument,
            "provider": "mock",
            "status": "waiting",
            "timeframes": {tf: None for tf in TIMEFRAMES},
            "message": "Multi-timeframe analysis is waiting for verified live candles.",
        }

    from app.live_engine.analysis import analyze_candles

    results: dict[str, dict] = {}
    for tf in TIMEFRAMES:
        try:
            provider = get_market_data_provider(settings.market_data_provider)
            candles = normalize_candles(
                await provider.get_candles(instrument, tf, limit=200)
            )
            validation = validate_candles(candles, timeframe=tf)
            if not candles or not validation.is_clean:
                results[tf] = {
                    "status": "rejected",
                    "reason": "Candle data failed validation.",
                }
                continue
            results[tf] = analyze_candles(candles)
        except Exception as exc:
            results[tf] = {
                "status": "unavailable",
                "reason": f"Provider error: {exc}",
            }

    available = [value for value in results.values() if value.get("status") == "available"]
    return {
        "instrument": instrument,
        "provider": settings.market_data_provider,
        "status": "available" if available else "waiting",
        "timeframes": results,
        "message": (
            "Multi-timeframe technical context only. No timeframe is converted "
            "into a BUY/SELL instruction by this endpoint."
        ),
    }


@router.get("/decision")
async def live_decision(
    instrument: str = Query("EUR/USD"),
    timeframe: str = Query("h1"),
) -> dict:
    """Return a read-only multi-factor decision from verified completed candles."""
    if instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Must be one of {INSTRUMENTS}.",
        )

    selected_timeframe = timeframe.lower()
    if selected_timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe {timeframe!r}. Must be one of {TIMEFRAMES}.",
        )

    settings = get_settings()
    if settings.market_data_provider == "mock":
        return {
            "instrument": instrument,
            "timeframe": selected_timeframe,
            "provider": "mock",
            "status": "waiting",
            "decision": "NO_TRADE",
            "message": "Decision engine is waiting for verified live candles; mock data cannot authorize a trade.",
            "trade_plan": None,
        }

    try:
        provider = get_market_data_provider(settings.market_data_provider)
        candles = normalize_candles(
            await provider.get_candles(instrument, selected_timeframe, limit=200)
        )
        candles = _completed_candles(candles, selected_timeframe)
        validation = validate_candles(candles, timeframe=selected_timeframe)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Decision data is unavailable: {exc}",
        ) from exc

    if len(candles) < 50 or not validation.is_clean:
        return {
            "instrument": instrument,
            "timeframe": selected_timeframe,
            "provider": settings.market_data_provider,
            "status": "rejected",
            "decision": "NO_TRADE",
            "message": "Decision engine refused insufficient or invalid candle data.",
            "data_quality": {
                "is_clean": validation.is_clean,
                "candle_count": len(candles),
                "ohlc_violations": len(validation.ohlc_violations),
                "duplicate_timestamps": len(validation.duplicate_timestamps),
                "unexpected_gaps": len(validation.unexpected_gaps),
            },
            "trade_plan": None,
        }

    from app.live_engine.candlesticks import detect_candlestick_patterns
    from app.news_engine.context import get_upcoming_macro_events
    from app.news_engine.macro_risk import compute_macro_event_risk
    from app.signal_engine.decision_engine import evaluate_trade_decision
    from app.technical_engine.features import calculate_feature_snapshots

    macro_events = await get_upcoming_macro_events(
        lookahead_hours=2,
        lookback_hours=0,
    )
    macro_risk = compute_macro_event_risk(
        instrument,
        macro_events,
    )

    snapshots = calculate_feature_snapshots(candles)
    if not snapshots:
        raise HTTPException(
            status_code=503,
            detail="Decision engine could not calculate technical features.",
        )

    patterns = detect_candlestick_patterns(candles)
    decision = evaluate_trade_decision(
        snapshots[-1],
        patterns,
        macro_risk_level=macro_risk.level,
    )

    # Complete the chain without opening or mutating a paper position:
    # market evidence -> multi-factor decision -> validated strategy -> risk -> paper eligibility.
    registry_path = Path(__file__).resolve().parents[4] / "research" / "results" / "validated_strategy_configs.json"
    configs: list[ValidatedStrategyConfig] = []
    if registry_path.exists():
        try:
            configs = [
                ValidatedStrategyConfig.from_dict(item)
                for item in json.loads(registry_path.read_text())
            ]
        except (OSError, ValueError, TypeError, KeyError):
            configs = []

    selection = select_strategy(
        instrument,
        selected_timeframe,
        configs,
        current_regime=snapshots[-1].regime,
    )

    risk_payload = {
        "status": "NOT_RUN",
        "state": None,
        "hierarchy_stage": None,
        "computed_risk_pct": None,
        "position_size": None,
        "reason": "No BUY/SELL decision reached the risk layer.",
    }
    paper_eligibility = {
        "eligible": False,
        "status": "NOT_ELIGIBLE",
        "reason": "Paper eligibility requires a BUY/SELL decision and an approved risk evaluation.",
        "persistent_state_changed": False,
        "real_broker_contacted": False,
        "execution_enabled": False,
    }

    if decision.decision in {"BUY", "SELL"} and decision.entry is not None and decision.stop_loss is not None:
        if selection.status == "TRADEABLE":
            account = AccountState(
                equity=10_000.0,
                peak_equity=10_000.0,
                daily_start_equity=10_000.0,
                daily_realized_pnl=0.0,
                daily_unrealized_pnl=0.0,
                open_positions_count=0,
                total_open_risk_pct=0.0,
                kill_switch_active=False,
            )
            risk = evaluate_risk(
                selection_result=selection,
                account=account,
                limits=RiskLimitsConfig(),
                direction="LONG" if decision.direction == "BUY" else "SHORT",
                entry_price=decision.entry,
                stop_price=decision.stop_loss,
                instrument_info=InstrumentTimeframeInfo(
                    instrument,
                    selected_timeframe,
                    mean_price=decision.entry,
                    price_precision_decimals=5,
                ),
            )
            risk_payload = {
                "status": "EVALUATED",
                "state": risk.state,
                "hierarchy_stage": risk.hierarchy_stage,
                "computed_risk_pct": risk.computed_risk_pct,
                "position_size": (
                    risk.position_sizing.final_position_size
                    if risk.position_sizing is not None
                    else None
                ),
                "reason": risk.reason,
            }
            if risk.state == "APPROVED":
                paper_eligibility = {
                    "eligible": True,
                    "status": "PAPER_ELIGIBLE",
                    "reason": "Multi-factor decision passed validated-strategy selection and the full risk hierarchy.",
                    "persistent_state_changed": False,
                    "real_broker_contacted": False,
                    "execution_enabled": False,
                }
            else:
                paper_eligibility["reason"] = f"Risk layer rejected the decision: {risk.reason}"
        else:
            paper_eligibility["reason"] = (
                f"Strategy Selector returned {selection.status}; "
                "a signal cannot bypass the validated-strategy gate."
            )

    return {
        "instrument": instrument,
        "timeframe": selected_timeframe,
        "provider": settings.market_data_provider,
        "status": "available",
        "decision": decision.decision,
        "methodology": decision.methodology,
        "macro_risk": {
            "level": macro_risk.level,
            "reason": macro_risk.reason,
            "triggering_event_count": len(macro_risk.triggering_events),
        },
        "data_quality": {
            "is_clean": validation.is_clean,
            "candle_count": len(candles),
            "last_candle": candles[-1].timestamp.isoformat(),
        },
        "market_evidence": {
            "last_close": snapshots[-1].close,
            "regime": snapshots[-1].regime,
            "rsi_14": snapshots[-1].rsi_14,
            "atr_14": snapshots[-1].atr_14,
            "atr_percent": snapshots[-1].atr_percent,
        },
        "strategy_gate": {
            "status": selection.status,
            "selected_config_id": selection.selected_config_id,
            "reason": selection.reason,
        },
        "trade_plan": decision.to_dict(),
        "risk": risk_payload,
        "paper_eligibility": paper_eligibility,
        "execution": {
            "enabled": False,
            "note": "This endpoint produces analysis only. It does not place orders.",
        },
    }
