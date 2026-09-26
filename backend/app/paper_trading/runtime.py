"""Live-data paper runtime.

This module is paper-only. It consumes the existing read-only decision
pipeline and then delegates every simulated entry/exit to PaperTradingEngine.
It never imports or calls broker/execution code.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.live import live_decision
from app.database.models import PaperRuntimePosition, PaperRuntimeState, PaperRuntimeTrade
from app.paper_trading.account import PaperAccountState
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.models import PaperPosition
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.risk_engine.risk_models import RiskLimitsConfig

ACCOUNT_KEY = "default_paper"
INSTRUMENTS = ("EUR/USD", "GBP/USD", "XAU/USD")
TIMEFRAMES = ("m5", "m15", "h1", "h4", "d1")
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
    state.realized_pnl = account.realized_pnl
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
    cycle_results = []
    now = datetime.now(timezone.utc)

    # First process exits using fresh prices. No new entry is evaluated until
    # existing positions have had a chance to close.
    current_prices: dict[str, float] = {}
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            try:
                response = await live_decision(instrument=instrument, timeframe=timeframe)
            except Exception as exc:
                cycle_results.append({
                    "instrument": instrument, "timeframe": timeframe,
                    "status": "UNAVAILABLE", "reason": str(exc),
                })
                continue

            plan = response.get("trade_plan") or {}
            entry = plan.get("entry")
            if entry is not None:
                current_prices[f"{instrument}:{timeframe}"] = float(entry)

    closed = engine.tick(current_prices, now)
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

            if response.get("paper_eligibility", {}).get("eligible") is not True:
                continue

            plan = response.get("trade_plan") or {}
            direction = "LONG" if plan.get("direction") == "BUY" else "SHORT" if plan.get("direction") == "SELL" else None
            if direction is None or plan.get("entry") is None or plan.get("stop_loss") is None:
                continue

            price = float(plan["entry"])
            result = engine.evaluate_and_maybe_open(
                instrument=instrument,
                timeframe=timeframe,
                direction=direction,
                entry_price=price,
                stop_price=float(plan["stop_loss"]),
                take_profit_price=(float(plan["take_profit"]) if plan.get("take_profit") is not None else None),
                current_prices={key: price},
                current_regime=response.get("market_evidence", {}).get("regime"),
                macro_event_risk=None,
            )
            cycle_results.append({
                "instrument": instrument,
                "timeframe": timeframe,
                "status": result.status,
                "reason": result.reason,
                "position_id": result.position.position_id if result.position else None,
            })

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
