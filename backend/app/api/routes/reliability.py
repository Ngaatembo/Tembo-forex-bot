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
