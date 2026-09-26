"""
Paper trading API — READ-ONLY by design. No endpoint here can open,
close, or modify a position; the Paper Trading Engine itself only
runs from backend scripts (see scripts/run_paper_trading_demonstration.py),
never from an HTTP request. This deliberately avoids anything
resembling an order-placement endpoint — the engine already enforces
the full Selector -> Gate -> Risk -> Kill-Switch chain internally, but
exposing a "place a paper trade" HTTP action would still invite exactly
the kind of misuse (arbitrary prices, no real market context) Step 5
explicitly warns against. These routes only ever report on state a
script already produced.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, desc
from datetime import datetime, timezone

router = APIRouter(tags=["paper-trading"])

_SNAPSHOT_PATH = str(
    Path(__file__).resolve().parents[4] / "research" / "results" / "paper_trading_demo_snapshot.json"
)


def _load_snapshot() -> dict:
    path = Path(_SNAPSHOT_PATH)
    if not path.exists():
        raise HTTPException(status_code=503, detail="No paper trading demonstration data available yet.")
    with open(path) as f:
        return json.load(f)


@router.get("/account/overview")
async def get_account_overview() -> dict:
    snapshot = _load_snapshot()
    account = snapshot["demo_account"]
    return {
        "account_id": account["account_id"],
        "mode": "PAPER_ONLY",
        "real_money": 0,
        "initial_equity": account["initial_equity"],
        "realized_pnl": account["realized_pnl"],
        "equity": account["equity"],
        "open_positions_count": len(account["open_positions"]),
        "generated_at": snapshot["generated_at"],
        "note": snapshot["note"],
    }


@router.get("/positions/open")
async def get_open_positions() -> list[dict]:
    return _load_snapshot()["demo_account"]["open_positions"]


@router.get("/positions/closed")
async def get_closed_positions() -> list[dict]:
    return _load_snapshot()["demo_account"]["closed_trades"]


@router.get("/risk/metrics")
async def get_risk_metrics() -> dict:
    from app.risk_engine.risk_models import RiskLimitsConfig
    limits = RiskLimitsConfig()
    snapshot = _load_snapshot()
    account = snapshot["demo_account"]
    return {
        "limits": {
            "max_risk_per_trade_pct": limits.max_risk_per_trade_pct,
            "max_total_open_risk_pct": limits.max_total_open_risk_pct,
            "max_daily_loss_pct": limits.max_daily_loss_pct,
            "max_drawdown_pct": limits.max_drawdown_pct,
            "max_simultaneous_positions": limits.max_simultaneous_positions,
            "max_exposure_pct": limits.max_exposure_pct,
        },
        "current": {
            "equity": account["equity"],
            "realized_pnl": account["realized_pnl"],
            "open_positions_count": len(account["open_positions"]),
        },
        "note": "Limits are the deployed RiskLimitsConfig defaults, documented as conservative "
                "starting points, not a claim of guaranteed safety.",
    }


@router.get("/performance")
async def get_performance() -> dict:
    snapshot = _load_snapshot()
    trades = snapshot["demo_account"]["closed_trades"]
    if not trades:
        return {"trade_count": 0, "total_realized_pnl": 0.0, "win_rate": None, "note": "No closed paper trades yet."}
    wins = sum(1 for t in trades if t["realized_pnl"] > 0)
    return {
        "trade_count": len(trades),
        "total_realized_pnl": sum(t["realized_pnl"] for t in trades),
        "win_rate": wins / len(trades),
        "note": "Computed directly from real closed-trade records — no statistic here is estimated or fabricated.",
    }


@router.get("/events")
async def get_events() -> list[dict]:
    snapshot = _load_snapshot()
    events = []
    for scenario_key, s in snapshot["scenarios"].items():
        events.append({"type": "DECISION", "scenario": scenario_key, "status": s["status"], "reason": s["reason"]})
    for t in snapshot["demo_account"]["closed_trades"]:
        events.append({
            "type": "POSITION_CLOSED", "instrument": t["instrument"], "timeframe": t["timeframe"],
            "exit_reason": t["exit_reason"], "realized_pnl": t["realized_pnl"], "timestamp": t["exit_time"],
        })
    return events


@router.get("/validation")
async def get_paper_validation() -> dict:
    """Run a deterministic, synthetic safety validation suite in memory."""
    from app.paper_trading.validation import run_paper_validation_suite

    return run_paper_validation_suite()


@router.get("/runtime/status")
async def get_runtime_status() -> dict:
    """Return persistent live-data paper runtime state; never mutates it."""
    from app.database.session import AsyncSessionLocal
    from app.database.models import PaperRuntimePosition, PaperRuntimeState

    async with AsyncSessionLocal() as db:
        state = (await db.execute(
            select(PaperRuntimeState).where(PaperRuntimeState.account_key == "default_paper")
        )).scalar_one_or_none()
        positions = (await db.execute(
            select(PaperRuntimePosition).where(
                PaperRuntimePosition.account_key == "default_paper",
                PaperRuntimePosition.status == "OPEN",
            )
        )).scalars().all()

    return {
        "status": "RUNNING" if state and state.last_cycle_at else "NOT_STARTED",
        "account_id": "default_paper",
        "initial_equity": state.initial_equity if state else 10000.0,
        "realized_pnl": state.realized_pnl if state else 0.0,
        "peak_equity": state.peak_equity if state else 10000.0,
        "open_positions": len(positions),
        "last_cycle_at": state.last_cycle_at.isoformat() if state and state.last_cycle_at else None,
        "execution_enabled": False,
        "broker_contacted": False,
    }


@router.get("/runtime/positions")
async def get_runtime_positions() -> list[dict]:
    """Return current persistent simulated positions."""
    from app.database.session import AsyncSessionLocal
    from app.database.models import PaperRuntimePosition

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PaperRuntimePosition).where(
                PaperRuntimePosition.account_key == "default_paper",
                PaperRuntimePosition.status == "OPEN",
            )
        )).scalars().all()

    return [
        {
            "position_id": row.position_id,
            "instrument": row.instrument,
            "timeframe": row.timeframe,
            "direction": row.direction,
            "entry_price": row.entry_price,
            "stop_price": row.stop_price,
            "take_profit_price": row.take_profit_price,
            "position_size": row.position_size,
            "candidate_config_id": row.candidate_config_id,
            "entry_time": row.entry_time.isoformat(),
            "periods_held": row.periods_held,
            "last_completed_candle_at": row.last_completed_candle_at.isoformat() if row.last_completed_candle_at else None,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/runtime/trades")
async def get_runtime_trades() -> list[dict]:
    """Return immutable closed paper trades from the live-data runtime."""
    from app.database.session import AsyncSessionLocal
    from app.database.models import PaperRuntimeTrade

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PaperRuntimeTrade)
            .where(PaperRuntimeTrade.account_key == "default_paper")
            .order_by(PaperRuntimeTrade.exit_time.desc())
        )).scalars().all()

    return [
        {
            "trade_id": row.trade_id,
            "position_id": row.position_id,
            "instrument": row.instrument,
            "timeframe": row.timeframe,
            "direction": row.direction,
            "entry_price": row.entry_price,
            "exit_price": row.exit_price,
            "position_size": row.position_size,
            "entry_time": row.entry_time.isoformat(),
            "exit_time": row.exit_time.isoformat(),
            "exit_reason": row.exit_reason,
            "realized_pnl": row.realized_pnl,
            "candidate_config_id": row.candidate_config_id,
        }
        for row in rows
    ]


@router.get("/runtime/metrics")
async def get_runtime_metrics() -> dict:
    """Compute operational and paper-performance metrics from persistent runtime records."""
    from collections import Counter, defaultdict
    from app.database.session import AsyncSessionLocal
    from app.database.models import PaperRuntimeTrade, SystemLog

    async with AsyncSessionLocal() as db:
        event_rows = (await db.execute(
            select(SystemLog)
            .where(SystemLog.component == "paper_runtime")
            .order_by(SystemLog.created_at.asc())
        )).scalars().all()
        trade_rows = (await db.execute(
            select(PaperRuntimeTrade)
            .where(PaperRuntimeTrade.account_key == "default_paper")
            .order_by(PaperRuntimeTrade.exit_time.asc())
        )).scalars().all()

    events = []
    for row in event_rows:
        try:
            events.append(json.loads(row.message))
        except (TypeError, ValueError):
            continue

    status_counts = Counter(str(e.get("status", "UNKNOWN")) for e in events)
    rejection_counts = Counter()
    instrument_counts = Counter()
    for event in events:
        status = str(event.get("status", "UNKNOWN"))
        if status not in {"CLOSED", "WAITING_NEW_CANDLE", "NO_SIGNAL"}:
            reason = str(event.get("reason") or "unspecified")
            rejection_counts[reason] += 1
        instrument = event.get("instrument")
        if instrument:
            instrument_counts[str(instrument)] += 1

    total_pnl = sum(float(t.realized_pnl) for t in trade_rows)
    wins = sum(1 for t in trade_rows if float(t.realized_pnl) > 0)
    losses = sum(1 for t in trade_rows if float(t.realized_pnl) < 0)
    gross_profit = sum(float(t.realized_pnl) for t in trade_rows if float(t.realized_pnl) > 0)
    gross_loss = sum(float(t.realized_pnl) for t in trade_rows if float(t.realized_pnl) < 0)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else None

    by_instrument = defaultdict(lambda: {"trades": 0, "realized_pnl": 0.0, "wins": 0, "losses": 0})
    for trade in trade_rows:
        bucket = by_instrument[trade.instrument]
        pnl = float(trade.realized_pnl)
        bucket["trades"] += 1
        bucket["realized_pnl"] += pnl
        bucket["wins"] += int(pnl > 0)
        bucket["losses"] += int(pnl < 0)

    return {
        "mode": "PAPER_ONLY",
        "cycles_observed": len({e.get("cycle_at") for e in events if e.get("cycle_at")}),
        "events_observed": len(events),
        "decision_status_counts": dict(status_counts),
        "rejection_reason_counts": dict(rejection_counts.most_common(25)),
        "instrument_event_counts": dict(instrument_counts),
        "performance": {
            "closed_trades": len(trade_rows),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(trade_rows)) if trade_rows else None,
            "realized_pnl": total_pnl,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "by_instrument": dict(by_instrument),
        },
        "execution_enabled": False,
        "broker_contacted": False,
        "note": "Metrics use only persistent runtime events and immutable closed paper trades; no estimates are generated.",
    }


@router.get("/runtime/events")
async def get_runtime_events(limit: int = 100) -> list[dict]:
    """Return the persistent audit trail produced by the paper runtime."""
    from app.database.session import AsyncSessionLocal
    from app.database.models import SystemLog

    safe_limit = max(1, min(limit, 500))
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(SystemLog)
            .where(SystemLog.component == "paper_runtime")
            .order_by(desc(SystemLog.created_at))
            .limit(safe_limit)
        )).scalars().all()

    events = []
    for row in rows:
        try:
            payload = json.loads(row.message)
        except (TypeError, ValueError):
            payload = {"message": row.message}
        events.append({
            "level": row.level,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            **payload,
        })
    return events
