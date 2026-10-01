"""Read-only contracts for the live trading cockpit.

The live cockpit is deliberately fail-closed: mock data is labelled as
mock and never exposed as a live quote, while real providers must return
validated candles before the cockpit can use them.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database.session import AsyncSessionLocal
from app.database.models import PaperRuntimePosition, PaperRuntimeState, MarketCandle

from app.api.routes.health import health_check
from app.research.forward_test import forward_test_config_ids, forward_test_limits, is_forward_test
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.risk_engine.risk_engine import evaluate_risk
from app.risk_engine.risk_models import AccountState, RiskLimitsConfig
from app.core.config import get_settings
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles
from app.strategy_engine.service import evaluate_live_strategy

router = APIRouter(prefix="/live", tags=["live"])

INSTRUMENTS = ("EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD")


def _is_synthetic_instrument(instrument: str) -> bool:
    return instrument.startswith("SYNTH:") and len(instrument) > len("SYNTH:")
TIMEFRAMES = ("m5", "m15", "h1", "h4", "d1")
_TIMEFRAME_DELTAS = {"m5": timedelta(minutes=5), "m15": timedelta(minutes=15), "h1": timedelta(hours=1), "h4": timedelta(hours=4), "d1": timedelta(days=1)}

def _completed_candles(candles, timeframe: str):
    now = datetime.now(timezone.utc)
    delta = _TIMEFRAME_DELTAS[timeframe]
    return [c for c in candles if c.timestamp + delta <= now]


async def _persist_verified_candles(candles) -> int:
    """Persist verified completed provider candles without affecting execution."""
    if not candles:
        return 0
    rows = [
        {
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
    async with AsyncSessionLocal() as session:
        stmt = insert(MarketCandle).values(rows)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_market_candle_identity")
        result = await session.execute(stmt)
        await session.commit()
        return int(result.rowcount or 0)


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
    selected = instrument if instrument in INSTRUMENTS or _is_synthetic_instrument(instrument) else "EUR/USD"
    selected_timeframe = timeframe.lower() if timeframe.lower() in TIMEFRAMES else "h1"
    provider = settings.market_data_provider
    data_status = health["market_data"]
    decision = "NO_TRADE"
    reason = (
        "Live market data is not verified, so Tembo fails closed instead of "
        "inventing an entry."
    )

    # The overview is also rendered above the detailed market workspace.
    # Populate its selected-market telemetry from the same verified provider
    # path so the UI cannot simultaneously show "data verified" and "no
    # market timestamp". This is read-only and never reaches execution.
    selected_price = None
    selected_last_update = None
    if data_status not in {"mock", "unavailable", "not_configured"}:
        try:
            provider_instance = get_market_data_provider(provider, selected)
            selected_price = await provider_instance.get_current_price(selected)
            overview_candles = normalize_candles(
                await provider_instance.get_candles(selected, selected_timeframe, limit=3)
            )
            overview_candles = _completed_candles(overview_candles, selected_timeframe)
            if overview_candles:
                overview_validation = validate_candles(
                    overview_candles, timeframe=selected_timeframe
                )
                if overview_validation.is_clean:
                    selected_last_update = overview_candles[-1].timestamp.isoformat()
        except Exception:
            # Detailed market/decision endpoints remain the authoritative
            # verification path. Overview must fail closed, not fabricate data.
            selected_price = None
            selected_last_update = None

    return {
        "mode": (
            "MT5_DEMO_READY"
            if settings.mt5_bridge_url
            else "MARKET_DATA_READY"
            if data_status not in {"mock", "unavailable", "not_configured"}
            else "PREPARING"
        ),
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
                "current_price": selected_price if symbol == selected else None,
                "last_update": selected_last_update if symbol == selected else None,
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


@router.get("/synthetic-symbols")
async def synthetic_symbols() -> dict:
    """Return currently active Deriv synthetic indices for the cockpit."""
    from app.data_engine.providers.deriv_synthetics import DerivSyntheticProvider
    try:
        symbols = await DerivSyntheticProvider().get_active_synthetics()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Deriv synthetic symbols are unavailable: {exc}",
        ) from exc
    return {
        "provider": "deriv",
        "status": "available",
        "symbols": symbols,
        "message": "Active synthetic symbols discovered from Deriv public market data.",
    }

@router.get("/market")
async def live_market(
    instrument: str = Query("EUR/USD"),
    timeframe: str = Query("h1"),
    limit: int = Query(120, ge=20, le=500),
) -> dict:
    """Return chart-ready quote/candle data without fabricating mock prices."""

    if instrument not in INSTRUMENTS and not _is_synthetic_instrument(instrument):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Use a supported forex/gold symbol or a discovered SYNTH:<DerivSymbol>.",
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
        provider = get_market_data_provider(settings.market_data_provider, instrument)
        current_price = await provider.get_current_price(instrument)
        candles = await provider.get_candles(
            instrument, selected_timeframe, limit=limit
        )
        candles = normalize_candles(candles)
        candles = _completed_candles(candles, selected_timeframe)
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

    # Seed/refresh the persistent market-candle history from the same verified
    # provider data used by the cockpit. Storage never opens or modifies trades.
    try:
        await _persist_verified_candles(candles)
    except Exception:
        # Display remains available if persistence is temporarily unavailable.
        pass

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
    if instrument not in INSTRUMENTS and not _is_synthetic_instrument(instrument):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Use a supported forex/gold symbol or a discovered SYNTH:<DerivSymbol>.",
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
        provider = get_market_data_provider(settings.market_data_provider, instrument)
        candles = await provider.get_candles(
            instrument, selected_timeframe, limit=200
        )
        candles = normalize_candles(candles)
        # Keep analysis aligned with market/decision endpoints: indicators
        # must never consume the currently-forming candle.
        candles = _completed_candles(candles, selected_timeframe)
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
    if instrument not in INSTRUMENTS and not _is_synthetic_instrument(instrument):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Use a supported forex/gold symbol or a discovered SYNTH:<DerivSymbol>.",
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
            provider = get_market_data_provider(settings.market_data_provider, instrument)
            candles = normalize_candles(
                await provider.get_candles(instrument, tf, limit=200)
            )
            candles = _completed_candles(candles, tf)
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
    if instrument not in INSTRUMENTS and not _is_synthetic_instrument(instrument):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid instrument {instrument!r}. Use a supported forex/gold symbol or a discovered SYNTH:<DerivSymbol>.",
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
        provider = get_market_data_provider(settings.market_data_provider, instrument)
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
    from app.news_engine.context import get_news_context, get_upcoming_macro_events
    from app.news_engine.macro_risk import compute_macro_event_risk
    from app.signal_engine.decision_engine import evaluate_trade_decision
    from app.technical_engine.features import calculate_feature_snapshots

    macro_events = await get_upcoming_macro_events(
        lookahead_hours=2,
        lookback_hours=0,
    )
    news_context = await get_news_context(instrument=instrument)
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
    technical_decision = evaluate_trade_decision(
        snapshots[-1],
        patterns,
        macro_risk_level=macro_risk.level,
    )

    # The researched configuration is now the strategy source of truth for
    # the live signal. The multi-factor engine remains visible as supporting
    # technical evidence, but it can no longer invent a BUY/SELL that the
    # selected researched strategy did not trigger.
    #
    # Complete the chain without opening or mutating a paper position:
    # market -> researched strategy -> macro gate -> research gate -> risk -> paper eligibility.
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

    selected_config = next(
        (config for config in configs if config.config_id == selection.selected_config_id),
        None,
    )
    strategy_result = (
        evaluate_live_strategy(
            candles,
            instrument,
            selected_config,
            atr=snapshots[-1].atr_14,
        )
        if selected_config is not None
        else None
    )

    strategy_signal = strategy_result.direction if strategy_result is not None else "WAIT"
    strategy_triggered = bool(strategy_result and strategy_result.triggered)
    macro_blocked = macro_risk.level in {"HIGH", "MEDIUM", "UNKNOWN"}

    if strategy_triggered and not macro_blocked and strategy_result.stop_loss is not None:
        effective_decision = strategy_signal
        effective_entry = strategy_result.entry
        effective_stop = strategy_result.stop_loss
        effective_target = strategy_result.take_profit
    else:
        effective_decision = "NO_TRADE"
        effective_entry = strategy_result.entry if strategy_result else None
        effective_stop = None
        effective_target = None

    strategy_reason = (
        strategy_result.reason
        if strategy_result is not None
        else selection.reason
    )
    if macro_blocked and strategy_triggered:
        strategy_reason = (
            f"{strategy_reason} Macro risk is {macro_risk.level}; "
            "the live strategy signal is blocked."
        )

    # Owner-approved forward test: a PROMISING config may run on paper and
    # the Deriv demo account only. All remaining gates still apply.
    forward_test = is_forward_test(
        selection.status, selection.selected_config_id, forward_test_config_ids()
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

    if (
        effective_decision in {"BUY", "SELL"}
        and effective_entry is not None
        and effective_stop is not None
    ):
        if selection.status == "TRADEABLE" or forward_test:
            # Risk must use the persistent paper account state, not a
            # fabricated constant balance. This keeps the cockpit's risk
            # calculation aligned with the actual paper runtime.
            async with AsyncSessionLocal() as risk_db:
                state = (await risk_db.execute(
                    select(PaperRuntimeState).where(
                        PaperRuntimeState.account_key == "default_paper"
                    )
                )).scalar_one_or_none()
                open_rows = (await risk_db.execute(
                    select(PaperRuntimePosition).where(
                        PaperRuntimePosition.account_key == "default_paper",
                        PaperRuntimePosition.status == "OPEN",
                    )
                )).scalars().all()

            if state is None or state.initial_equity is None:
                # Unknown account state is deliberately fail-closed.
                account = AccountState(kill_switch_active=True)
            else:
                equity = float(state.initial_equity) + float(state.realized_pnl or 0.0)
                open_risk_amount = sum(float(row.risk_amount or 0.0) for row in open_rows)
                total_open_risk_pct = open_risk_amount / equity if equity > 0 else 1.0
                account = AccountState(
                    equity=equity,
                    peak_equity=float(state.peak_equity or equity),
                    daily_start_equity=float(state.daily_start_equity or equity),
                    daily_realized_pnl=float(state.daily_realized_pnl or 0.0),
                    daily_unrealized_pnl=0.0,
                    open_positions_count=len(open_rows),
                    total_open_risk_pct=total_open_risk_pct,
                    kill_switch_active=bool(state.kill_switch_active),
                )

            risk = evaluate_risk(
                selection_result=selection,
                account=account,
                limits=forward_test_limits(RiskLimitsConfig()) if forward_test else RiskLimitsConfig(),
                forward_test=forward_test,
                direction="LONG" if effective_decision == "BUY" else "SHORT",
                entry_price=effective_entry,
                stop_price=effective_stop,
                instrument_info=InstrumentTimeframeInfo(
                    instrument,
                    selected_timeframe,
                    mean_price=effective_entry,
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
                    "status": "FORWARD_TEST_ELIGIBLE" if forward_test else "PAPER_ELIGIBLE",
                    "reason": (
                        "Forward test: the PROMISING strategy's live signal passed macro risk and the full "
                        "risk hierarchy at half the normal per-trade risk. Paper and Deriv demo only."
                        if forward_test
                        else "Live researched strategy signal passed the validated-strategy selection and the full risk hierarchy."
                    ),
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
        "decision": effective_decision,
        "methodology": "RESEARCHED_STRATEGY_LIVE_V1",
        "technical_decision": technical_decision.to_dict(),
        "macro_risk": {
            "level": macro_risk.level,
            "reason": macro_risk.reason,
            "triggering_event_count": len(macro_risk.triggering_events),
        },
        "news": {
            "status": news_context.status,
            "freshness": news_context.freshness,
            "provider": news_context.provider,
            "last_successful_fetch": news_context.last_successful_fetch.isoformat() if news_context.last_successful_fetch else None,
            "error": news_context.error,
            "headlines": [
                {
                    "news_id": item.news_id,
                    "timestamp": item.timestamp.isoformat(),
                    "headline": item.headline,
                    "source": item.source,
                    "url": item.url,
                }
                for item in news_context.relevant_news[:5]
            ],
        },
        "macro_events": [
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "currency": event.currency,
                "country": event.country,
                "event_name": event.event_name,
                "importance": event.importance,
                "previous": event.previous,
                "forecast": event.forecast,
                "actual": event.actual,
                "source": event.source,
                "time_confirmed": event.time_confirmed,
            }
            for event in (macro_events or [])
        ],
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
            "live_evaluation": (
                {
                    "config_id": strategy_result.config_id,
                    "strategy_family": strategy_result.strategy_family,
                    "status": strategy_result.status,
                    "direction": strategy_result.direction,
                    "triggered": strategy_result.triggered,
                    "entry": strategy_result.entry,
                    "stop_loss": strategy_result.stop_loss,
                    "take_profit": strategy_result.take_profit,
                    "risk_reward": strategy_result.risk_reward,
                    "reason": strategy_result.reason,
                    "parameters": strategy_result.parameter_summary,
                }
                if strategy_result is not None
                else None
            ),
        },
        "trade_plan": {
            "decision": effective_decision,
            "direction": strategy_signal,
            "entry": effective_entry,
            "stop_loss": effective_stop,
            "take_profit": effective_target,
            "risk_reward": strategy_result.risk_reward if strategy_result else None,
            "reason": strategy_reason,
        },
        "risk": risk_payload,
        "paper_eligibility": paper_eligibility,
        "forward_test": {
            "active": forward_test,
            "config_id": selection.selected_config_id if forward_test else None,
            "max_risk_per_trade_pct": forward_test_limits(RiskLimitsConfig()).max_risk_per_trade_pct if forward_test else None,
            "note": (
                "This PROMISING strategy is being forward-tested on paper and the Deriv demo account only."
                if forward_test
                else None
            ),
        },
        "execution": {
            "enabled": False,
            "note": "This endpoint produces analysis only. It does not place orders.",
        },
    }
