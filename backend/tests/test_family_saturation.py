from app.research.family_saturation import (
    CandidateEvidenceSummary, compute_family_saturation,
)
from app.research.hypothesis import HypothesisType
from app.research.verdict import Verdict


def h1_like_record(candidate_id="cand_h1", verdict=Verdict.OUT_OF_SAMPLE_FAILED, experiment_count=2):
    """Mirrors H1's real shape: one candidate, Phase 8 + Phase 8.1
    combined into experiment_count=2, official verdict OUT_OF_SAMPLE_FAILED."""
    return CandidateEvidenceSummary(
        candidate_id=candidate_id, family=HypothesisType.MEAN_REVERSION, verdict=verdict,
        experiment_count=experiment_count, created_at="2026-08-30T11:10:00+00:00",
    )


def breakout_record(candidate_id, created_at="2026-08-30T12:17:00+00:00"):
    """Mirrors one breakout lookback's real shape: REJECTED, folding its
    Phase 9 + Phase 9.1 regime-filter follow-ups into one candidate."""
    return CandidateEvidenceSummary(
        candidate_id=candidate_id, family=HypothesisType.BREAKOUT, verdict=Verdict.REJECTED,
        experiment_count=4, created_at=created_at,  # 1 unfiltered + 3 pre-registered regime filters
    )


def test_correct_family_grouping():
    records = [h1_like_record(), breakout_record("cand_breakout_20")]
    result = compute_family_saturation(records)
    assert HypothesisType.MEAN_REVERSION in result
    assert HypothesisType.BREAKOUT in result
    assert result[HypothesisType.MEAN_REVERSION].hypothesis_count == 1
    assert result[HypothesisType.BREAKOUT].hypothesis_count == 1


def test_correct_experiment_counting():
    records = [h1_like_record(experiment_count=2)]
    result = compute_family_saturation(records)
    assert result[HypothesisType.MEAN_REVERSION].experiment_count == 2


def test_oos_failure_counted_correctly():
    records = [h1_like_record(verdict=Verdict.OUT_OF_SAMPLE_FAILED)]
    result = compute_family_saturation(records)
    fam = result[HypothesisType.MEAN_REVERSION]
    assert fam.oos_failure_count == 1
    assert fam.rejected_count == 0


def test_repeated_rejection_triggers_saturated_status():
    """Mirrors breakout's real history: 3 lookbacks, all REJECTED."""
    records = [
        breakout_record("cand_breakout_20"), breakout_record("cand_breakout_40"),
        breakout_record("cand_breakout_60"),
    ]
    result = compute_family_saturation(records)
    fam = result[HypothesisType.BREAKOUT]
    assert fam.rejected_count == 3
    assert fam.negative_evidence_density == 1.0
    assert fam.saturation_status == "SATURATED"


def test_promising_candidate_not_counted_as_negative():
    records = [
        breakout_record("cand_breakout_20"), breakout_record("cand_breakout_40"),
        CandidateEvidenceSummary(
            candidate_id="cand_breakout_new", family=HypothesisType.BREAKOUT,
            verdict=Verdict.PROMISING, experiment_count=1, created_at="2026-09-01T00:00:00+00:00",
        ),
    ]
    result = compute_family_saturation(records)
    fam = result[HypothesisType.BREAKOUT]
    assert fam.promising_count == 1
    assert fam.negative_evidence_density == 2 / 3  # only the 2 REJECTED count as negative
    assert fam.saturation_status == "ACTIVE"  # below the 80% density threshold


def test_too_few_candidates_stays_active_not_saturated():
    """Even 100% negative isn't SATURATED yet if there are too few attempts to trust the pattern."""
    records = [breakout_record("cand_1"), breakout_record("cand_2")]  # only 2, below default min of 3
    result = compute_family_saturation(records)
    assert result[HypothesisType.BREAKOUT].negative_evidence_density == 1.0
    assert result[HypothesisType.BREAKOUT].saturation_status == "ACTIVE"


def test_configurable_thresholds_change_outcome():
    records = [breakout_record("cand_1"), breakout_record("cand_2")]
    default_result = compute_family_saturation(records)
    lenient_result = compute_family_saturation(records, min_hypotheses_for_saturation=2)
    assert default_result[HypothesisType.BREAKOUT].saturation_status == "ACTIVE"
    assert lenient_result[HypothesisType.BREAKOUT].saturation_status == "SATURATED"


def test_no_double_counting_when_records_correctly_grouped():
    """
    Direct proof this module is 'dumb': feeding it ONE record with
    experiment_count=2 (correct grouping, as Chunk 5 should do) vs TWO
    separate records (incorrect double-counting) produces DIFFERENT
    hypothesis_count — proving the aggregator faithfully reflects
    whatever it's given, and that correct grouping is the caller's job.
    """
    correctly_grouped = [h1_like_record(experiment_count=2)]
    incorrectly_split = [
        h1_like_record(candidate_id="cand_h1_phase8", experiment_count=1),
        h1_like_record(candidate_id="cand_h1_phase8_1", experiment_count=1),
    ]
    correct_result = compute_family_saturation(correctly_grouped)
    wrong_result = compute_family_saturation(incorrectly_split)

    assert correct_result[HypothesisType.MEAN_REVERSION].hypothesis_count == 1
    assert wrong_result[HypothesisType.MEAN_REVERSION].hypothesis_count == 2  # double-counted if split incorrectly
    # experiment_count happens to match in this example (2 either way),
    # but hypothesis_count (how many DISTINCT research lines) does not —
    # that's the count saturation actually cares about.


def test_empty_family_reports_untested():
    result = compute_family_saturation([])
    assert result == {}


def test_deterministic_output():
    records = [h1_like_record(), breakout_record("cand_breakout_20")]
    first = compute_family_saturation(records)
    second = compute_family_saturation(records)
    assert first == second


def test_latest_experiment_timestamp_tracked():
    records = [
        breakout_record("cand_1", created_at="2026-08-01T00:00:00+00:00"),
        breakout_record("cand_2", created_at="2026-08-30T12:17:00+00:00"),
    ]
    result = compute_family_saturation(records)
    assert result[HypothesisType.BREAKOUT].latest_experiment_at == "2026-08-30T12:17:00+00:00"
