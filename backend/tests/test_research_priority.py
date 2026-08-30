from app.research.family_saturation import FamilySaturation
from app.research.hypothesis import HypothesisType
from app.research.research_priority import compute_research_priority


def saturation(status="ACTIVE", density=0.5, count=3):
    return FamilySaturation(
        family=HypothesisType.BREAKOUT, hypothesis_count=count, experiment_count=count * 2,
        rejected_count=int(count * density), oos_failure_count=0, overfit_failure_count=0,
        promising_count=0, latest_experiment_at="2026-08-30T12:17:00+00:00",
        negative_evidence_density=density, saturation_status=status,
    )


def test_h1_like_case_not_high_priority_merely_because_oos_pf_was_1000():
    """H1's real gate status was CLOSED (verdict OUT_OF_SAMPLE_FAILED) —
    priority must be CLOSED, never HIGH, regardless of how close to 1.0 it was."""
    result = compute_research_priority("CLOSED", edge_level="WEAK", family_saturation=saturation())
    assert result.priority == "CLOSED"


def test_saturated_failed_family_gets_low_priority():
    """Breakout's real shape: repeated REJECTED verdicts, family SATURATED."""
    sat = saturation(status="SATURATED", density=1.0, count=3)
    result = compute_research_priority("REJECT_EARLY", edge_level="WEAK", family_saturation=sat)
    assert result.priority == "CLOSED"  # individually gate-closed takes precedence

    # A candidate that's ROBUSTNESS_REQUIRED (not individually gate-closed)
    # but sits in a saturated family should still be pulled down to LOW.
    result2 = compute_research_priority("ROBUSTNESS_REQUIRED", edge_level="MODERATE", family_saturation=sat)
    assert result2.priority == "LOW"


def test_strong_development_failed_oos_not_high_merely_because_dev_was_strong():
    """Defense in depth: even if someone passed a WEAK edge with a
    strong-sounding reason, gate_status=CLOSED alone forces CLOSED."""
    result = compute_research_priority("CLOSED", edge_level="STRONG", family_saturation=saturation())
    assert result.priority == "CLOSED"


def test_promising_candidate_with_missing_robustness_gets_higher_priority_than_rejected_family():
    """Direct implementation of the project's own stated example."""
    sat = saturation(status="ACTIVE")
    unresolved_promising = compute_research_priority("ROBUSTNESS_REQUIRED", edge_level="STRONG", family_saturation=sat)
    rejected_family = compute_research_priority("REJECT_EARLY", edge_level="WEAK", family_saturation=sat)
    assert unresolved_promising.priority == "HIGH"
    assert rejected_family.priority == "CLOSED"


def test_missing_robustness_directs_research_not_declares_success():
    """HIGH priority for STRONG-edge-but-unproven must be framed as an
    open question, never as a success/profitability claim."""
    result = compute_research_priority("ROBUSTNESS_REQUIRED", edge_level="STRONG", family_saturation=saturation())
    assert result.priority == "HIGH"
    assert "unresolved" in result.reason.lower() or "missing" in result.reason.lower() or "blocked" in result.reason.lower()
    assert "profit" not in result.reason.lower()  # never framed as a profitability claim


def test_weak_edge_robustness_required_gets_medium_not_high():
    result = compute_research_priority("ROBUSTNESS_REQUIRED", edge_level="MODERATE", family_saturation=saturation())
    assert result.priority == "MEDIUM"


def test_promising_gate_status_is_high():
    result = compute_research_priority("PROMISING", edge_level="STRONG", family_saturation=saturation())
    assert result.priority == "HIGH"


def test_paper_candidate_gate_status_is_high():
    result = compute_research_priority("PAPER_CANDIDATE", edge_level="STRONG", family_saturation=saturation())
    assert result.priority == "HIGH"


def test_single_promising_candidate_not_buried_by_saturated_family():
    """A real positive lead inside an otherwise-saturated family keeps HIGH priority."""
    sat = saturation(status="SATURATED", density=0.9, count=10)
    result = compute_research_priority("PROMISING", edge_level="STRONG", family_saturation=sat)
    assert result.priority == "HIGH"


def test_research_gate_status_is_medium():
    result = compute_research_priority("RESEARCH", edge_level="UNKNOWN", family_saturation=saturation())
    assert result.priority == "MEDIUM"


def test_deterministic_output():
    sat = saturation()
    first = compute_research_priority("ROBUSTNESS_REQUIRED", edge_level="STRONG", family_saturation=sat)
    second = compute_research_priority("ROBUSTNESS_REQUIRED", edge_level="STRONG", family_saturation=sat)
    assert first == second
