"""
Reconstructs real StrategyCandidate records from the actual saved
Phase 8/8.1/9/9.1 research JSON — no new backtests, no invented
evidence. Documents exactly where synthetic experiment_id references
were needed (Phase 8.1/9/9.1 never saved formal ResearchExperiment
records with real experiment_id values — only Phase 8 did).

Two-pass structure, and why: research_priority needs family_saturation,
which needs EVERY candidate's verdict computed first. So:
  Pass 1: for each candidate, compute Verdict, Scorecard, GateResult,
          and a CandidateEvidenceSummary (for saturation).
  Pass 2 (after family_saturation is computed once, across all
          candidates): compute each candidate's research_priority using
          its own gate/edge plus the now-known family_saturation for
          its family, then construct the final immutable StrategyCandidate.
"""

import json

from app.research.family_saturation import CandidateEvidenceSummary, compute_family_saturation
from app.research.historical_reconstruction import (
    cost_tier_summaries_from_h1_robustness, cost_tier_summaries_from_phase9_results,
    parameter_neighborhood_from_h1_robustness, period_summaries_from_metrics,
    period_summaries_from_phase9_tier, regime_dependence_from_h1_robustness,
    statistical_evidence_from_h1_robustness,
)
from app.research.hypothesis import HypothesisType
from app.research.overfitting import compute_overfitting_diagnostics
from app.research.research_gate import compute_research_gate
from app.research.research_priority import compute_research_priority
from app.research.scorecard import compute_scorecard
from app.research.strategy_candidate import StrategyCandidate, new_candidate_id, save_candidate
from app.research.verdict import compute_verdict

RESULTS_DIR = "/home/claude/ai-trading-platform/research/results"


def _load(filename: str) -> dict:
    with open(f"{RESULTS_DIR}/{filename}") as f:
        return json.load(f)


def gather_h1_candidate():
    phase8 = _load("phase_8_research_experiments.json")
    h1_exp = next(e for e in phase8 if e["hypothesis_id"].startswith("range_extreme_reversion"))
    robustness = _load("phase_8_1_h1_robustness.json")

    periods = period_summaries_from_metrics(h1_exp["metrics"])
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)

    cost_tiers = cost_tier_summaries_from_h1_robustness(robustness["cost_sensitivity"])
    neighborhood = (
        parameter_neighborhood_from_h1_robustness(robustness["neighborhood_results"], prefix="distance_")
        + parameter_neighborhood_from_h1_robustness(robustness["neighborhood_results"], prefix="atr_ceiling_")
    )
    statistical_evidence = statistical_evidence_from_h1_robustness(
        robustness["statistical_analysis"], actual_win_rate=periods["out_of_sample"].win_rate,
    )
    regime_dependence = regime_dependence_from_h1_robustness(robustness["regime_dependence"])

    scorecard = compute_scorecard(
        periods, verdict, overfitting, parameter_neighborhood=neighborhood,
        cost_tier_summaries=cost_tiers, statistical_evidence=statistical_evidence,
        regime_dependence=regime_dependence,
    )
    gate = compute_research_gate(verdict, scorecard, overfitting)

    return dict(
        name="H1 — Range-Extreme Mean Reversion", family=HypothesisType.MEAN_REVERSION,
        description="LONG near the 20-candle low / SHORT near the high, filtered to calm volatility.",
        experiment_ids=(h1_exp["experiment_id"], "phase8_1_h1_robustness_diagnostic"),
        lineage_note="Phase 8 initial test + Phase 8.1 dedicated robustness/statistical follow-up "
                     "(diagnostic only — Phase 8.1 never had its own formal ResearchExperiment record).",
        verdict=verdict, scorecard=scorecard, overfitting=overfitting, gate=gate,
        created_at=h1_exp["created_at"],
    )


def gather_h2_candidate():
    phase8 = _load("phase_8_research_experiments.json")
    h2_exp = next(e for e in phase8 if e["hypothesis_id"].startswith("volatility_squeeze_breakout"))

    periods = period_summaries_from_metrics(h2_exp["metrics"])
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    scorecard = compute_scorecard(periods, verdict, overfitting)
    gate = compute_research_gate(verdict, scorecard, overfitting)

    return dict(
        name="H2 — Volatility Squeeze Breakout", family=HypothesisType.VOLATILITY,
        description="LONG/SHORT on a compressed 20-candle range with an SMA50-slope directional bias.",
        experiment_ids=(h2_exp["experiment_id"],),
        lineage_note="Phase 8 only — no follow-up research was ever conducted on H2.",
        verdict=verdict, scorecard=scorecard, overfitting=overfitting, gate=gate,
        created_at=h2_exp["created_at"],
    )


def gather_breakout_candidate(lookback: int):
    phase9 = _load("phase_9_breakout_results.json")
    phase9_1 = _load("phase_9_1_regime_filtered_breakout.json")

    lookback_key = str(lookback)
    lookback_results = phase9["results"][lookback_key]
    periods = period_summaries_from_phase9_tier(lookback_results["BASE"])
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    cost_tiers = cost_tier_summaries_from_phase9_results(lookback_results)
    scorecard = compute_scorecard(periods, verdict, overfitting, cost_tier_summaries=cost_tiers)
    gate = compute_research_gate(verdict, scorecard, overfitting)

    filter_labels = [k for k in phase9_1["results"][lookback_key] if k != "UNFILTERED"]

    return dict(
        name=f"Market-Structure Breakout (lookback={lookback})", family=HypothesisType.BREAKOUT,
        description=f"Breaks of the prior {lookback}-candle range, ATR-stop + max-hold exit.",
        experiment_ids=(
            f"phase9_breakout_lookback{lookback}_unfiltered",
            *[f"phase9_1_breakout_lookback{lookback}_{label}" for label in filter_labels],
        ),
        lineage_note=f"Phase 9 initial test + Phase 9.1's {len(filter_labels)} regime-filter follow-ups "
                     f"for this lookback (all synthetic experiment_id references — Phase 9/9.1 never "
                     f"saved formal ResearchExperiment records).",
        verdict=verdict, scorecard=scorecard, overfitting=overfitting, gate=gate,
        created_at=phase9["metadata"]["dataset"]["period_end"],
    )


def main():
    print("Gathering evidence for all candidates (Pass 1)...")
    raw_candidates = [
        gather_h1_candidate(), gather_h2_candidate(),
        gather_breakout_candidate(20), gather_breakout_candidate(40), gather_breakout_candidate(60),
    ]

    saturation_input = [
        CandidateEvidenceSummary(
            candidate_id=f"pending_{i}", family=rc["family"], verdict=rc["verdict"],
            experiment_count=len(rc["experiment_ids"]), created_at=rc["created_at"],
        )
        for i, rc in enumerate(raw_candidates)
    ]
    family_saturation = compute_family_saturation(saturation_input)
    print(f"Family saturation computed across {len(family_saturation)} families.")

    registry_path = f"{RESULTS_DIR}/phase_10_strategy_candidates.json"
    print(f"\nBuilding final StrategyCandidate records (Pass 2), saving to {registry_path} ...")

    for rc in raw_candidates:
        sat = family_saturation[rc["family"]]
        priority = compute_research_priority(rc["gate"].status, rc["scorecard"].edge.level, sat)

        candidate = StrategyCandidate(
            candidate_id=new_candidate_id(rc["name"]), name=rc["name"], family=rc["family"],
            description=rc["description"], experiment_ids=rc["experiment_ids"],
            parent_candidate_id=None, lineage_note=rc["lineage_note"],
            research_priority=priority.priority, gate_status=rc["gate"].status,
            created_at=rc["created_at"], verdict=rc["verdict"].value,
        )
        save_candidate(candidate, registry_path)
        print(
            f"  {candidate.name}: family={rc['family'].value} verdict={rc['verdict'].value} "
            f"gate={rc['gate'].status} priority={priority.priority}"
        )

    print(f"\nDone. {len(raw_candidates)} candidates saved.")


if __name__ == "__main__":
    main()
