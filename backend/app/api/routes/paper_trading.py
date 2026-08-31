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
