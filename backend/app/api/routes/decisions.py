"""
Integration-milestone API — the frontend's primary decision source.

CRITICAL DESIGN GUARANTEE: final_decision can only ever be "NO_TRADE"
or "PAPER_TRADE_APPROVED" — "LIVE_TRADE_APPROVED" is not a value this
code can produce; there is no branch that assigns it. Even when a
future candidate reaches Selector status "TRADEABLE", this endpoint
still cannot approve a paper trade today because no live market data
feed exists in this backend to run app.risk_engine.evaluate_risk()
against (it needs a real entry/stop price) — that limitation is
reported honestly in the response, not papered over with a fabricated
price.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig

router = APIRouter(tags=["decisions"])

_REGISTRY_PATH = str(
    Path(__file__).resolve().parents[4] / "research" / "results" / "validated_strategy_configs.json"
)
_VALID_TIMEFRAMES = {"m5", "m15", "h1", "h4", "d1"}


def _load_configs() -> list[ValidatedStrategyConfig]:
    path = Path(_REGISTRY_PATH)
    if not path.exists():
        return []
    with open(path) as f:
        records = json.load(f)
    return [ValidatedStrategyConfig.from_dict(r) for r in records]


def _validate_timeframe(timeframe: str) -> str:
    normalized = timeframe.lower()
    if normalized not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe {timeframe!r}. Must be one of {sorted(_VALID_TIMEFRAMES)}.")
    return normalized


@router.get("/decisions")
async def get_decision(
    instrument: str = Query(..., description="e.g. 'XAU/USD'"),
    timeframe: str = Query(..., description="e.g. 'h1'"),
) -> dict:
    timeframe = _validate_timeframe(timeframe)
    configs = _load_configs()
    selection = select_strategy(instrument, timeframe, configs)

    selected_config = None
    research_gate_status = None
    regime_evidence = None
    if selection.selected_config_id:
        match = next((c for c in configs if c.config_id == selection.selected_config_id), None)
        if match:
            selected_config = {
                "config_id": match.config_id, "candidate_id": match.candidate_id,
                "strategy_family": match.strategy_family.value, "parameters": match.parameters,
                "gate_status": match.gate_status, "verdict": match.verdict,
                "statistical_level": match.statistical_level,
            }
            research_gate_status = match.gate_status
            regime_evidence = match.regime_evidence

    if selection.status == "TRADEABLE":
        final_decision = "NO_TRADE"
        reason = (
            f"{selection.reason} However, no live market data feed is connected yet, so the "
            "Risk Engine cannot evaluate a real entry/stop and no paper trade can be approved."
        )
    else:
        final_decision = "NO_TRADE"
        reason = selection.reason

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "has_validated_edge": selection.status == "TRADEABLE",
        "selector_status": selection.status,
        "selected_config": selected_config,
        "research_gate_status": research_gate_status,
        "final_decision": final_decision,
        "reason": reason,
        "regime_evidence": regime_evidence,
        "considered_candidates": [
            {"config_id": c.config_id, "gate_status": c.gate_status, "reason": c.reason}
            for c in selection.considered
        ],
        "research_recommendation": selection.research_recommendation,
    }


@router.get("/strategy/select")
async def get_strategy_selection(
    instrument: str = Query(...), timeframe: str = Query(...),
) -> dict:
    timeframe = _validate_timeframe(timeframe)
    configs = _load_configs()
    selection = select_strategy(instrument, timeframe, configs)
    return {
        "instrument": selection.instrument, "timeframe": selection.timeframe,
        "status": selection.status, "selected_config_id": selection.selected_config_id,
        "reason": selection.reason,
        "considered": [{"config_id": c.config_id, "gate_status": c.gate_status, "reason": c.reason} for c in selection.considered],
        "research_recommendation": selection.research_recommendation,
    }


@router.get("/instruments")
async def get_researched_instruments() -> list[dict]:
    """Every instrument/timeframe combination this project has ever
    actually researched — so the frontend never has to guess or
    hard-code a universe. Not every combination here is tradeable;
    it just means research data exists to query via /decisions."""
    configs = _load_configs()
    seen = {}
    for c in configs:
        key = (c.instrument, c.timeframe)
        seen.setdefault(key, {"instrument": c.instrument, "timeframe": c.timeframe, "researched_families": []})
        family = c.strategy_family.value
        if family not in seen[key]["researched_families"]:
            seen[key]["researched_families"].append(family)
    return list(seen.values())
