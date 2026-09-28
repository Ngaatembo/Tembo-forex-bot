"""Read-only reliability diagnostics.

These endpoints report guardrail state. They never execute trades.
"""

from fastapi import APIRouter, Query

from app.reliability.guardrails import (
    detect_drift,
    drawdown_governor,
    evaluate_cost_gate,
    monte_carlo_trade_resample,
)

router = APIRouter(prefix="/reliability", tags=["reliability"])


@router.get("/cost-gate")
async def cost_gate(
    entry: float,
    stop_loss: float,
    take_profit: float,
    estimated_cost: float = Query(0.0, ge=0.0),
) -> dict:
    result = evaluate_cost_gate(entry, stop_loss, take_profit, estimated_cost)
    return {"status": result.status, "reason": result.reason, "cost_to_target_ratio": result.cost_to_target_ratio}


@router.get("/drawdown")
async def drawdown(drawdown_pct: float = Query(..., ge=0.0)) -> dict:
    result = drawdown_governor(drawdown_pct)
    return {"status": result.status, "size_multiplier": result.size_multiplier, "reason": result.reason}


@router.post("/drift")
async def drift(payload: dict) -> dict:
    result = detect_drift(payload.get("baseline", []), payload.get("live", []))
    return {
        "status": result.status,
        "baseline_mean": result.baseline_mean,
        "live_mean": result.live_mean,
        "difference": result.difference,
        "reason": result.reason,
    }


@router.post("/monte-carlo")
async def monte_carlo(payload: dict) -> dict:
    result = monte_carlo_trade_resample(payload.get("returns", []), payload.get("simulations", 1000))
    return {
        "simulations": result.simulations,
        "worst_return": result.worst_return,
        "median_return": result.median_return,
        "loss_probability": result.loss_probability,
    }


@router.get("/runtime")
async def reliability_runtime() -> dict:
    """Report the persistent paper runtime's drawdown governor state.

    This is diagnostic only: it never changes risk, positions, or execution.
    The drawdown is based on persisted paper-runtime equity state.
    """
    from app.database.session import AsyncSessionLocal
    from app.database.models import PaperRuntimeState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        state = (await db.execute(
            select(PaperRuntimeState).where(PaperRuntimeState.account_key == "default_paper")
        )).scalar_one_or_none()

    if state is None:
        result = drawdown_governor(0.0)
        return {
            "status": "NOT_STARTED",
            "drawdown_pct": 0.0,
            "governor": result.status,
            "size_multiplier": result.size_multiplier,
            "reason": "PAPER_RUNTIME_NOT_STARTED",
        }

    initial_equity = float(state.initial_equity or 0.0)
    realized_pnl = float(state.realized_pnl or 0.0)
    peak_equity = float(state.peak_equity or initial_equity)
    current_equity = initial_equity + realized_pnl
    if peak_equity <= 0:
        result = drawdown_governor(float("nan"))
        drawdown_pct = None
    else:
        drawdown_pct = max(0.0, (peak_equity - current_equity) / peak_equity * 100.0)
        result = drawdown_governor(drawdown_pct)

    return {
        "status": "AVAILABLE",
        "drawdown_pct": drawdown_pct,
        "governor": result.status,
        "size_multiplier": result.size_multiplier,
        "reason": result.reason,
        "equity_basis": "INITIAL_PLUS_REALIZED_PNL",
    }

@router.get("/status")
async def reliability_status() -> dict:
    return {
        "status": "AVAILABLE",
        "mode": "READ_ONLY_DIAGNOSTICS",
        "execution": "DISABLED",
        "guardrails": [
            "EXECUTION_COST_GATE",
            "DRAWDOWN_GOVERNOR",
            "DRIFT_DETECTION",
            "MONTE_CARLO_ROBUSTNESS",
        ],
        "policy": "FAIL_CLOSED",
    }
