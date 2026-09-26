"""Live-data paper runtime.

This module is paper-only. It consumes the existing read-only decision
pipeline and then delegates every simulated entry/exit to PaperTradingEngine.
It never imports or calls broker/execution code.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.live import live_decision
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles
from app.core.config import get_settings
from app.database.models import PaperRuntimePosition, PaperRuntimeState, PaperRuntimeTrade, SystemLog
from app.paper_trading.account import PaperAccountState
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.models import PaperPosition
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.risk_engine.risk_models import RiskLimitsConfig
from app.news_engine.models import MacroEventRisk

ACCOUNT_KEY = "default_paper"
INSTRUMENTS = ("EUR/USD", "GBP/USD", "XAU/USD")
TIMEFRAMES = ("h1",)
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "research" / "results" / "validated_strategy_configs.json"


def _configs() -> list[ValidatedStrategyConfig]:
    try:
        return [ValidatedStrategyConfig.from_dict(x) for x in json.loads(REGISTRY_PATH.read_text())]
    except (OSError, ValueError, TypeError, KeyError):
        return []


async def _get_or_create_state(db: AsyncSession) -> PaperRuntimeState:
    state = (await db.execute(
        select(PaperRuntimeState).where(PaperRuntimeState.account_key == ACCOUNT_KEY)
    )).scalar_one_or_none()
    if state is None:
        state = PaperRuntimeState(account_key=ACCOUNT_KEY)
        db.add(state)
        await db.flush()
    return state


async def _load_account(db: AsyncSession) -> tuple[PaperAccountState, PaperRuntimeState, dict[str, PaperPosition]]:
    state = await _get_or_create_state(db)
    rows = (await db.execute(
        select(PaperRuntimePosition).where(
            PaperRuntimePosition.account_key == ACCOUNT_KEY,
            PaperRuntimePosition.status == "OPEN",
        )
    )).scalars().all()

    today = datetime.now(timezone.utc).date().isoformat()
    if state.session_date != today:
        # Start a new risk session from current equity. Historical closed
        # trades remain immutable; only the daily risk baseline resets.
        state.daily_start_equity = state.initial_equity + state.realized_pnl
        state.daily_realized_pnl = 0.0
        state.session_date = today

    account = PaperAccountState(
        account_id=ACCOUNT_KEY,
        initial_equity=state.initial_equity,
        daily_start_equity=state.daily_start_equity,
        kill_switch_active=state.kill_switch_active,
        realized_pnl=state.realized_pnl,
        _peak_equity=state.peak_equity,
    )
    positions: dict[str, PaperPosition] = {}
    for row in rows:
        p = PaperPosition(
            position_id=row.position_id,
            instrument=row.instrument,
            timeframe=row.timeframe,
            direction=row.direction,
            entry_price=row.entry_price,
            entry_time=row.entry_time,
            stop_price=row.stop_price,
            position_size=row.position_size,
            candidate_config_id=row.candidate_config_id,
            take_profit_price=row.take_profit_price,
            max_holding_periods=row.max_holding_periods,
            periods_held=row.periods_held,
            status=row.status,
        )
        account.open_position(p, row.risk_amount)
        positions[p.key()] = p
    return account, state, positions


async def _persist_account(db: AsyncSession, account: PaperAccountState, state: PaperRuntimeState) -> None:
    previous_realized = state.realized_pnl
    state.realized_pnl = account.realized_pnl
    state.daily_realized_pnl += account.realized_pnl - previous_realized
    state.peak_equity = account._peak_equity
    state.kill_switch_active = account.kill_switch_active
    state.updated_at = datetime.now(timezone.utc)

    existing = {
        row.position_id: row
        for row in (await db.execute(
            select(PaperRuntimePosition).where(PaperRuntimePosition.account_key == ACCOUNT_KEY)
        )).scalars().all()
    }
    open_ids = {p.position_id for p in account.open_positions.values()}

    for position in account.open_positions.values():
        row = existing.get(position.position_id)
        risk_amount = account.position_risk_amounts[position.key()]
        if row is None:
            row = PaperRuntimePosition(
                account_key=ACCOUNT_KEY,
                position_id=position.position_id,
                instrument=position.instrument,
                timeframe=position.timeframe,
                direction=position.direction,
                entry_price=position.entry_price,
                stop_price=position.stop_price,
                take_profit_price=position.take_profit_price,
                position_size=position.position_size,
                candidate_config_id=position.candidate_config_id,
                entry_time=position.entry_time,
                periods_held=position.periods_held,
                max_holding_periods=position.max_holding_periods,
                risk_amount=risk_amount,
                status="OPEN",
            )
            db.add(row)
        else:
            row.periods_held = position.periods_held
            row.status = position.status
            row.risk_amount = risk_amount

    for position_id, row in existing.items():
        if position_id not in open_ids and row.status == "OPEN":
            row.status = "CLOSED"

    # Closed trades are append-only. Only write records not already present.
    existing_trade_ids = {
        x for x in (await db.execute(
            select(PaperRuntimeTrade.trade_id).where(PaperRuntimeTrade.account_key == ACCOUNT_KEY)
        )).scalars().all()
    }
    for trade in account.closed_trades:
        if trade.trade_id in existing_trade_ids:
            continue
        db.add(PaperRuntimeTrade(
            account_key=ACCOUNT_KEY,
            trade_id=trade.trade_id,
            position_id=trade.position_id,
            instrument=trade.instrument,
            timeframe=trade.timeframe,
            direction=trade.direction,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            position_size=trade.position_size,
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            exit_reason=trade.exit_reason,
            realized_pnl=trade.realized_pnl,
            candidate_config_id=trade.candidate_config_id,
        ))

    state.last_cycle_at = datetime.now(timezone.utc)


async def run_paper_cycle(db: AsyncSession) -> dict:
    """Run one idempotent paper cycle over the configured cockpit universe."""
    account, state, _ = await _load_account(db)
    configs = _configs()
    engine = PaperTradingEngine(account, configs, RiskLimitsConfig())
    # Position IDs must remain unique across service restarts. Recover the
    # highest persisted counter, including previously closed positions.
    all_position_ids = (await db.execute(
        select(PaperRuntimePosition.position_id).where(
            PaperRuntimePosition.account_key == ACCOUNT_KEY
        )
    )).scalars().all()
    counters = []
    for position_id in all_position_ids:
        try:
            counters.append(int(str(position_id).rsplit("_", 1)[1]))
        except (ValueError, IndexError):
            continue
    engine._position_counter = max(counters, default=0)
    cycle_results = []
    now = datetime.now(timezone.utc)

    # Process exits first, but only fetch a live quote for instruments that
    # actually have an open position. Entry decisions fetch their own
    # validated H1 candle set, so prefetching 120 candles here would duplicate
    # provider calls and can trigger rate limits.
    current_prices: dict[str, float] = {}
    advance_holding_period_keys: set[str] = set()
    open_keys = list(account.open_positions.keys())
    provider = get_market_data_provider(get_settings().market_data_provider)
    for key in open_keys:
        instrument, timeframe = key.rsplit(":", 1)
        try:
            current_prices[key] = float(await provider.get_current_price(instrument))
            # Exit monitoring remains frequent, but max-holding periods advance
            # only when a new completed candle for the position timeframe exists.
            candles = normalize_candles(
                await provider.get_candles(instrument, timeframe, limit=2)
            )
            validation = validate_candles(candles, timeframe=timeframe)
            if validation.is_clean and candles:
                latest_candle_at = candles[-1].timestamp
                row = (await db.execute(
                    select(PaperRuntimePosition).where(
                        PaperRuntimePosition.account_key == ACCOUNT_KEY,
                        PaperRuntimePosition.position_id == account.open_positions[key].position_id,
                    )
                )).scalar_one_or_none()
                if row is not None:
                    if row.last_completed_candle_at is None or latest_candle_at > row.last_completed_candle_at:
                        advance_holding_period_keys.add(key)
                        row.last_completed_candle_at = latest_candle_at
        except Exception as exc:
            cycle_results.append({
                "instrument": instrument, "timeframe": timeframe,
                "status": "UNAVAILABLE", "reason": str(exc),
            })

    closed = engine.tick(
        current_prices,
        now,
        advance_holding_period_keys=advance_holding_period_keys,
    )
    for trade in closed:
        cycle_results.append({
            "instrument": trade.instrument,
            "timeframe": trade.timeframe,
            "status": "CLOSED",
            "reason": trade.exit_reason,
            "realized_pnl": trade.realized_pnl,
        })

    # Re-evaluate entries after exits. The existing live decision endpoint is
    # the sole source of signal + strategy/risk eligibility.
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            key = f"{instrument}:{timeframe}"
            if key in account.open_positions:
                continue
            try:
                response = await live_decision(instrument=instrument, timeframe=timeframe)
            except Exception as exc:
                cycle_results.append({
                    "instrument": instrument, "timeframe": timeframe,
                    "status": "UNAVAILABLE", "reason": str(exc),
                })
                continue

            plan = response.get("trade_plan") or {}
            if response.get("decision") not in {"BUY", "SELL"}:
                cycle_results.append({
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "status": "NO_SIGNAL",
                    "reason": response.get("message") or "Live decision did not authorize a directional paper candidate.",
                })
                continue
            direction = "LONG" if plan.get("direction") == "BUY" else "SHORT" if plan.get("direction") == "SELL" else None
            if direction is None or plan.get("entry") is None or plan.get("stop_loss") is None:
                continue

            price = float(plan["entry"])
            macro = response.get("macro_event_risk") or {}
            macro_level = macro.get("level")
            macro_event_risk = MacroEventRisk(
                level=macro_level,
                reason=str(macro.get("reason") or ""),
                triggering_events=(),
            ) if macro_level else None
            result = engine.evaluate_and_maybe_open(
                instrument=instrument,
                timeframe=timeframe,
                direction=direction,
                entry_price=price,
                stop_price=float(plan["stop_loss"]),
                take_profit_price=(float(plan["take_profit"]) if plan.get("take_profit") is not None else None),
                current_prices={key: current_prices.get(key, price)},
                current_regime=None,
                macro_event_risk=macro_event_risk,
            )
            if result.position is not None:
                entry_candle_raw = (response.get("data_quality") or {}).get("last_candle")
                if entry_candle_raw:
                    try:
                        entry_candle_at = datetime.fromisoformat(entry_candle_raw)
                        row = (await db.execute(
                            select(PaperRuntimePosition).where(
                                PaperRuntimePosition.account_key == ACCOUNT_KEY,
                                PaperRuntimePosition.position_id == result.position.position_id,
                            )
                        )).scalar_one_or_none()
                        if row is not None:
                            row.last_completed_candle_at = entry_candle_at
                    except ValueError:
                        pass
            cycle_results.append({
                "instrument": instrument,
                "timeframe": timeframe,
                "status": result.status,
                "reason": result.reason,
                "position_id": result.position.position_id if result.position else None,
            })

    # Persist a compact audit trail for every cycle event. SystemLog is
    # append-only and does not affect trading decisions.
    for event in cycle_results:
        db.add(SystemLog(
            level="INFO" if event.get("status") not in {"UNAVAILABLE", "ERROR"} else "WARNING",
            component="paper_runtime",
            message=json.dumps({
                "account_id": ACCOUNT_KEY,
                "cycle_at": now.isoformat(),
                **event,
            }, default=str),
        ))

    await _persist_account(db, account, state)
    await db.commit()

    return {
        "status": "OK",
        "account_id": ACCOUNT_KEY,
        "cycle_at": now.isoformat(),
        "open_positions": len(account.open_positions),
        "realized_pnl": account.realized_pnl,
        "events": cycle_results,
        "execution_enabled": False,
        "broker_contacted": False,
    }
