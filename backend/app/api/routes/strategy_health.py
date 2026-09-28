"""Read-only strategy registry health diagnostics.

This surface describes what the research gate currently supports. It never
selects a strategy for execution and never opens a position.
"""

import json
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig

router = APIRouter(prefix="/strategy-health", tags=["strategy-health"])

_REGISTRY_PATH = Path(__file__).resolve().parents[4] / "research" / "results" / "validated_strategy_configs.json"


def _load_configs() -> list[ValidatedStrategyConfig]:
    if not _REGISTRY_PATH.exists():
        raise HTTPException(status_code=503, detail="Validated strategy registry is unavailable.")
    try:
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        return [ValidatedStrategyConfig(**item) for item in raw]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Validated strategy registry is invalid: {exc}") from exc


@router.get("/status")
async def strategy_health_status() -> dict:
    configs = _load_configs()
    gate_counts = Counter(c.gate_status for c in configs)
    verdict_counts = Counter(c.verdict for c in configs)
    instruments = sorted({c.instrument for c in configs})
    timeframes = sorted({c.timeframe for c in configs})
    return {
        "status": "AVAILABLE",
        "mode": "READ_ONLY_RESEARCH_REGISTRY",
        "execution": "DISABLED",
        "registry": {
            "config_count": len(configs),
            "gate_counts": dict(sorted(gate_counts.items())),
            "verdict_counts": dict(sorted(verdict_counts.items())),
            "instruments": instruments,
            "timeframes": timeframes,
        },
        "policy": "NO_VALIDATED_EDGE_IS_A_VALID_OUTCOME",
    }


@router.get("/instrument")
async def instrument_health(
    instrument: str = Query(..., min_length=3),
    timeframe: str = Query("h1"),
    current_regime: str | None = Query(None),
) -> dict:
    configs = _load_configs()
    result = select_strategy(instrument, timeframe, configs, current_regime=current_regime)
    return {
        "instrument": result.instrument,
        "timeframe": result.timeframe,
        "current_regime": current_regime,
        "status": result.status,
        "selected_config_id": result.selected_config_id,
        "reason": result.reason,
        "research_recommendation": result.research_recommendation,
        "considered": [
            {
                "config_id": c.config_id,
                "gate_status": c.gate_status,
                "reason": c.reason,
            }
            for c in result.considered
        ],
    }
