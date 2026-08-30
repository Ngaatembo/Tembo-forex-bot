"""
Historical reconstruction helpers.

Converts the SAVED JSON shapes produced by Phase 8/8.1/9/9.1's scripts
into the existing typed objects (BacktestSummary, and the dict/list
shapes scorecard.py already expects) — no new backtests are run here,
and no evidence is invented. Every function is a pure data
transformation over an already-loaded dict.

WHY THIS EXISTS SEPARATELY FROM THE RECONSTRUCTION SCRIPT: these
shapes (Phase 8's proper ResearchExperiment.metrics vs. Phase 9's
ad-hoc nested tier/period/summary dicts vs. Phase 8.1's diagnostic
JSON) are inconsistent with each other because those phases predate
Phase 10's StrategyCandidate model — they were never designed to feed
into it. These functions are the (documented, tested) translation
layer, kept separate from real file I/O so they're testable with
small fixture dicts instead of the actual multi-megabyte research files.
"""

from app.backtesting.models import BacktestSummary


def backtest_summary_from_dict(d: dict) -> BacktestSummary:
    """Both Phase 8's ResearchExperiment.metrics entries and Phase 9's
    nested tier/period entries store BacktestSummary as a flat dict
    with matching field names — this works for both."""
    return BacktestSummary(**d)


def period_summaries_from_metrics(metrics: dict) -> dict[str, BacktestSummary]:
    """metrics = {"development": {...}, "validation": {...}, "out_of_sample": {...}}
    — Phase 8's ResearchExperiment.metrics shape, and also matches
    Phase 9's results[lookback][tier] shape once each period's
    ['summary'] sub-dict is extracted by the caller (see
    period_summaries_from_phase9_tier)."""
    return {label: backtest_summary_from_dict(d) for label, d in metrics.items()}


def period_summaries_from_phase9_tier(tier_data: dict) -> dict[str, BacktestSummary]:
    """Phase 9's shape nests an extra level: tier_data[period]['summary'],
    with payoff/holding-time stats alongside — only ['summary'] is a BacktestSummary."""
    return {label: backtest_summary_from_dict(d["summary"]) for label, d in tier_data.items()}


def cost_tier_summaries_from_h1_robustness(cost_sensitivity: dict, period: str = "out_of_sample") -> dict[str, BacktestSummary]:
    """Phase 8.1's cost_sensitivity = {"LOW": {dev/val/oos...}, "BASE": {...}, "HIGH": {...}}."""
    return {tier: backtest_summary_from_dict(periods[period]) for tier, periods in cost_sensitivity.items()}


def cost_tier_summaries_from_phase9_results(lookback_results: dict, period: str = "out_of_sample") -> dict[str, BacktestSummary]:
    """Phase 9's shape: lookback_results[tier][period]['summary']."""
    return {
        tier: backtest_summary_from_dict(periods[period]["summary"])
        for tier, periods in lookback_results.items()
        if tier in ("LOW", "BASE", "HIGH")
    }


def parameter_neighborhood_from_h1_robustness(
    neighborhood_results: dict, prefix: str, period: str = "out_of_sample"
) -> list[BacktestSummary]:
    """
    neighborhood_results is keyed by e.g. "distance_0.0004", "atr_ceiling_0.0012".
    `prefix` selects which parameter's neighborhood to extract (e.g. "distance_"
    or "atr_ceiling_") — the two parameters were varied one at a time
    (Phase 8.1), so they must be assessed as separate neighborhoods, not merged.
    """
    return [
        backtest_summary_from_dict(periods[period])
        for key, periods in neighborhood_results.items()
        if key.startswith(prefix)
    ]


def statistical_evidence_from_h1_robustness(statistical_analysis: dict, actual_win_rate: float) -> dict:
    """
    Maps Phase 8.1's saved key names to the shape scorecard.py's
    _statistical_score expects (wilson_ci / bootstrap_ci_total_pnl /
    breakeven_win_rate / actual_win_rate) — the underlying numbers are
    identical, only the key names differ between what Phase 8.1 saved
    and what Chunk 2's scorecard.py was written to read.
    """
    return {
        "wilson_ci": tuple(statistical_analysis["wilson_95_ci"]),
        "bootstrap_ci_total_pnl": tuple(statistical_analysis["bootstrap_95_ci_total_pnl"]),
        "breakeven_win_rate": statistical_analysis["breakeven_win_rate"],
        "actual_win_rate": actual_win_rate,
    }


def regime_dependence_from_h1_robustness(regime_dependence: dict) -> dict:
    """Phase 8.1's saved shape already matches scorecard.py's expected
    {regime_label: {"net_pnl": ..., ...}} shape exactly — passthrough,
    no transform needed. Kept as an explicit named function anyway so
    the reconstruction script never reaches into raw JSON directly."""
    return regime_dependence
