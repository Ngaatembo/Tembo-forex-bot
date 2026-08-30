"""
Family saturation — detects when a HypothesisType (reused directly
from Phase 7, not a new taxonomy) has accumulated enough negative
research evidence that further variations there have low research
value.

INPUT SHAPE, and why it looks like this: this module does NOT read
StrategyCandidate + ResearchExperiment records directly and does NOT
run any lookups or backtests. It takes a flat list of
CandidateEvidenceSummary — one entry per LOGICAL research candidate
(not per raw experiment). This is deliberate: H1's Phase 8 experiment
and its Phase 8.1 robustness follow-up are ONE candidate with
experiment_count=2, not two separate entries — avoiding double-
counting is the responsibility of whoever constructs this list
(Chunk 5, from real StrategyCandidate records), not something this
aggregator can or should infer on its own. This module is
deliberately "dumb" and purely arithmetic — see
test_no_double_counting_when_records_correctly_grouped for a direct
proof that feeding it one combined record vs. two separate records
for the same research produces different (and correctly different)
counts, i.e. the correctness of the aggregation depends entirely on
how the input list was built.

THRESHOLDS (documented, not tuned to any specific family's actual
results):
  MIN_HYPOTHESES_FOR_SATURATION_JUDGMENT = 3 — you need at least a
    few independent attempts within a family before "repeated
    failure" is a meaningful pattern rather than one or two unlucky
    tries. Deliberately small (this counts distinct research
    candidates, not individual trades — verdict.py's own
    MIN_TRADES_PER_PERIOD=10 threshold is the analogous "enough data
    points to trust a pattern" reasoning at the trade level; 3 is the
    equivalent reasoning applied at the much coarser
    candidate-history level).
  NEGATIVE_DENSITY_SATURATION_THRESHOLD = 0.8 — at least 80% of tested
    candidates in the family must be negative before it's called
    SATURATED, deliberately leaving room for a family with, say, 1
    promising candidate out of 5 tested to NOT be marked saturated —
    a real live positive lead should never be buried by a majority of
    unrelated negative attempts in the same family.
"""

from dataclasses import asdict, dataclass
from typing import Optional

from app.research.hypothesis import HypothesisType
from app.research.verdict import Verdict

MIN_HYPOTHESES_FOR_SATURATION_JUDGMENT = 3
NEGATIVE_DENSITY_SATURATION_THRESHOLD = 0.8

_NEGATIVE_VERDICTS = {Verdict.REJECTED, Verdict.OUT_OF_SAMPLE_FAILED, Verdict.OVERFIT_SUSPECTED}
_POSITIVE_VERDICTS = {Verdict.PROMISING, Verdict.VALIDATED_FOR_PAPER_TRADING}


@dataclass(frozen=True)
class CandidateEvidenceSummary:
    """One entry per LOGICAL candidate (already de-duplicated across
    parent/child follow-ups by whoever builds this list — see module docstring)."""
    candidate_id: str
    family: HypothesisType
    verdict: Verdict
    experiment_count: int  # how many experiments/follow-ups this one candidate aggregates
    created_at: str  # ISO timestamp of the most recent evidence for this candidate


@dataclass(frozen=True)
class FamilySaturation:
    family: HypothesisType
    hypothesis_count: int
    experiment_count: int
    rejected_count: int
    oos_failure_count: int
    overfit_failure_count: int
    promising_count: int
    latest_experiment_at: Optional[str]
    negative_evidence_density: float
    saturation_status: str  # "UNTESTED" | "ACTIVE" | "SATURATED"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["family"] = self.family.value
        return d


def _saturation_status(
    hypothesis_count: int, negative_density: float,
    min_hypotheses: int, density_threshold: float,
) -> str:
    if hypothesis_count == 0:
        return "UNTESTED"
    if hypothesis_count < min_hypotheses:
        return "ACTIVE"  # too few attempts yet to judge saturation either way
    if negative_density >= density_threshold:
        return "SATURATED"
    return "ACTIVE"


def compute_family_saturation(
    records: list[CandidateEvidenceSummary],
    min_hypotheses_for_saturation: int = MIN_HYPOTHESES_FOR_SATURATION_JUDGMENT,
    negative_density_threshold: float = NEGATIVE_DENSITY_SATURATION_THRESHOLD,
) -> dict[HypothesisType, FamilySaturation]:
    by_family: dict[HypothesisType, list[CandidateEvidenceSummary]] = {}
    for r in records:
        by_family.setdefault(r.family, []).append(r)

    results: dict[HypothesisType, FamilySaturation] = {}
    for family, family_records in by_family.items():
        hypothesis_count = len(family_records)
        experiment_count = sum(r.experiment_count for r in family_records)
        rejected = sum(1 for r in family_records if r.verdict == Verdict.REJECTED)
        oos_failed = sum(1 for r in family_records if r.verdict == Verdict.OUT_OF_SAMPLE_FAILED)
        overfit = sum(1 for r in family_records if r.verdict == Verdict.OVERFIT_SUSPECTED)
        promising = sum(1 for r in family_records if r.verdict in _POSITIVE_VERDICTS)

        negative_count = sum(1 for r in family_records if r.verdict in _NEGATIVE_VERDICTS)
        negative_density = negative_count / hypothesis_count if hypothesis_count else 0.0

        latest = max((r.created_at for r in family_records), default=None)

        results[family] = FamilySaturation(
            family=family, hypothesis_count=hypothesis_count, experiment_count=experiment_count,
            rejected_count=rejected, oos_failure_count=oos_failed, overfit_failure_count=overfit,
            promising_count=promising, latest_experiment_at=latest,
            negative_evidence_density=negative_density,
            saturation_status=_saturation_status(
                hypothesis_count, negative_density, min_hypotheses_for_saturation, negative_density_threshold,
            ),
        )
    return results
