"""
Read-only research endpoints. Every route here is GET — there is no
POST/PUT/DELETE anywhere in this router, and none is needed: hypothesis
registration and experiment execution happen via the Python API
(app.research.hypothesis_registry, app.research.research_experiment)
today, run from trusted scripts, not from an HTTP request body. This
is deliberate: an endpoint that accepted a hypothesis definition over
HTTP would be a much larger attack surface than one that only ever
reads from the on-disk registries these scripts already produced.

No endpoint here executes anything, calls a broker, or accepts
arbitrary code in any form — see test_research_security_boundary.py's
API-level check.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.research.family_saturation import CandidateEvidenceSummary, compute_family_saturation
from app.research.hypothesis import HypothesisType
from app.research.hypothesis_registry import get_hypothesis, list_hypotheses
from app.research.research_experiment import load_research_experiments
from app.research.strategy_candidate import load_candidates
from app.research.verdict import Verdict

router = APIRouter(prefix="/research", tags=["research"])

# Same on-disk registries the research scripts write to — see
# scripts/run_phase7_hypotheses.py.
_HYPOTHESIS_REGISTRY_PATH = str(
    Path(__file__).resolve().parents[4] / "research" / "results" / "phase_7_hypothesis_registry.json"
)
_EXPERIMENT_REGISTRY_PATH = str(
    Path(__file__).resolve().parents[4] / "research" / "results" / "phase_7_research_experiments.json"
)
_CANDIDATE_REGISTRY_PATH = str(
    Path(__file__).resolve().parents[4] / "research" / "results" / "phase_10_strategy_candidates.json"
)


@router.get("/hypotheses")
async def get_hypotheses() -> list[dict]:
    return [h.to_dict() for h in list_hypotheses(_HYPOTHESIS_REGISTRY_PATH, latest_only=True)]


@router.get("/hypotheses/{hypothesis_id}")
async def get_hypothesis_by_id(hypothesis_id: str) -> dict:
    hypothesis = get_hypothesis(hypothesis_id, _HYPOTHESIS_REGISTRY_PATH)
    if hypothesis is None:
        raise HTTPException(status_code=404, detail=f"No hypothesis with id {hypothesis_id!r}")
    return hypothesis.to_dict()


@router.get("/experiments")
async def get_experiments() -> list[dict]:
    return load_research_experiments(_EXPERIMENT_REGISTRY_PATH)


@router.get("/experiments/{experiment_id}")
async def get_experiment_by_id(experiment_id: str) -> dict:
    records = load_research_experiments(_EXPERIMENT_REGISTRY_PATH)
    match = next((r for r in records if r["experiment_id"] == experiment_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"No experiment with id {experiment_id!r}")
    return match


@router.get("/baseline")
async def get_baseline() -> dict:
    from app.research.baseline import FROZEN_BASELINE_HISTORICAL_REFERENCE, FROZEN_BASELINE_ID
    return {"baseline_id": FROZEN_BASELINE_ID, "historical_reference": FROZEN_BASELINE_HISTORICAL_REFERENCE}


@router.get("/candidates")
async def get_candidates() -> list[dict]:
    """
    Every StrategyCandidate on record — H1, H2, and the three breakout
    lookbacks as of Phase 10 Chunk 5 — with its verdict, research gate
    status, and research priority. Read-only: this endpoint cannot
    create, modify, or delete anything, and nothing behind it can
    place an order or reach a broker.
    """
    return [c.to_dict() for c in load_candidates(_CANDIDATE_REGISTRY_PATH)]


@router.get("/candidates/{candidate_id}")
async def get_candidate_by_id(candidate_id: str) -> dict:
    candidates = load_candidates(_CANDIDATE_REGISTRY_PATH)
    match = next((c for c in candidates if c.candidate_id == candidate_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"No candidate with id {candidate_id!r}")
    return match.to_dict()


@router.get("/families")
async def get_families() -> list[dict]:
    """
    Per-HypothesisType saturation summary, computed live from every
    on-record candidate (never cached/stale) — see family_saturation.py
    for exactly what SATURATED means and why.
    """
    candidates = load_candidates(_CANDIDATE_REGISTRY_PATH)
    summaries = [
        CandidateEvidenceSummary(
            candidate_id=c.candidate_id, family=c.family,
            verdict=Verdict(c.verdict) if c.verdict else Verdict.INCONCLUSIVE,
            experiment_count=len(c.experiment_ids), created_at=c.created_at,
        )
        for c in candidates
    ]
    saturation = compute_family_saturation(summaries)
    return [s.to_dict() for s in saturation.values()]
