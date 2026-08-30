"""
Deterministic research scorecard.

NOT a profitability predictor. Every category is a categorical
judgment (STRONG/MODERATE/WEAK/UNKNOWN) with a short, deterministic,
traceable reason — never an opaque numeric score, never a weighted
sum. Missing evidence is always UNKNOWN, never assumed positive — see
each category's docstring for exactly what triggers UNKNOWN.

Reuses existing infrastructure rather than recomputing it:
  - EDGE is derived primarily from the existing Verdict (verdict.py),
    not a second profitability judgment.
  - ROBUSTNESS incorporates the existing OverfittingDiagnostics
    (overfitting.py) directly.
  - RISK reads payoff-ratio directly from BacktestSummary's own
    average_win/average_loss fields — no new calculation duplicating
    statistics_analysis.py's compute_payoff_stats() (which requires
    raw trades; a summary-level estimate is what's available when only
    aggregate BacktestSummary records exist, as is the case for most
    saved experiment history).
  - STATISTICAL and cost-tier evidence for REALISM are OPTIONAL inputs
    — not every candidate has had statistics_analysis.py's Wilson/
    bootstrap analysis or a full LOW/BASE/HIGH cost sweep run against
    it (Phase 9's breakout experiments do; H1's Phase 8 experiment
    alone does not, until Phase 8.1's dedicated follow-up). Absent
    means UNKNOWN, not a guess.

THRESHOLDS: every numeric threshold below (drawdown bands, payoff
ratio cutoff) is a documented, arbitrary starting choice — same
philosophy as regime.py's thresholds in Phase 5 and overfitting.py's
in Phase 7. Never tuned against any actual candidate's results.
"""

from dataclasses import asdict, dataclass
from typing import Optional

from app.backtesting.models import BacktestSummary
from app.research.overfitting import OverfittingDiagnostics
from app.research.verdict import Verdict

DRAWDOWN_STRONG_MAX = 0.20    # < 20% max drawdown
DRAWDOWN_WEAK_MIN = 0.40      # >= 40% max drawdown
PAYOFF_RATIO_STRONG_MIN = 1.5
PAYOFF_RATIO_WEAK_MAX = 0.8


@dataclass(frozen=True)
class CategoryScore:
    level: str  # "STRONG" | "MODERATE" | "WEAK" | "UNKNOWN"
    reason: str


@dataclass(frozen=True)
class Scorecard:
    edge: CategoryScore
    robustness: CategoryScore
    risk: CategoryScore
    statistical: CategoryScore
    realism: CategoryScore
    underlying_verdict: str  # Verdict.value, carried through for traceability — never recomputed differently

    def to_dict(self) -> dict:
        return asdict(self)


def _edge_score(verdict: Verdict, out_of_sample: BacktestSummary) -> CategoryScore:
    """
    Reuses the existing Verdict directly — this is the safeguard against
    "strong development alone producing a strong EDGE": Verdict already
    encodes OUT_OF_SAMPLE_FAILED/REJECTED regardless of how good
    development looked, and EDGE inherits that classification rather
    than re-deriving a competing judgment from development data alone.
    """
    if verdict == Verdict.INCONCLUSIVE:
        return CategoryScore("UNKNOWN", "Verdict is INCONCLUSIVE — insufficient trade count to judge edge.")
    if verdict in (Verdict.PROMISING, Verdict.VALIDATED_FOR_PAPER_TRADING):
        return CategoryScore(
            "STRONG",
            f"Verdict is {verdict.value} — profit factor > 1.0 held across development, validation, and out-of-sample.",
        )
    if verdict == Verdict.OVERFIT_SUSPECTED:
        return CategoryScore("MODERATE", "Verdict is OVERFIT_SUSPECTED — some periods show an edge, but inconsistently.")
    if verdict == Verdict.OUT_OF_SAMPLE_FAILED:
        pf = out_of_sample.profit_factor
        if pf is not None and 0.95 <= pf <= 1.05:
            return CategoryScore(
                "WEAK",
                f"Verdict is OUT_OF_SAMPLE_FAILED with out-of-sample profit factor {pf:.3f} — "
                "close to breakeven, but development working while out-of-sample did not is still a failure by the verdict rule.",
            )
        return CategoryScore("WEAK", "Verdict is OUT_OF_SAMPLE_FAILED — profitable in development, not out-of-sample.")
    return CategoryScore("WEAK", f"Verdict is {verdict.value} — development itself showed no edge.")


def _robustness_score(
    verdict: Verdict, overfitting: OverfittingDiagnostics,
    parameter_neighborhood: Optional[list[BacktestSummary]],
) -> CategoryScore:
    if verdict in (Verdict.REJECTED, Verdict.OUT_OF_SAMPLE_FAILED, Verdict.INCONCLUSIVE):
        return CategoryScore("WEAK", f"Verdict is {verdict.value} — not enough of an edge exists to assess robustness of.")

    overfitting_note = (
        "Overfitting diagnostics raised at least one flag."
        if overfitting.any_flag_raised else "No overfitting diagnostic flags raised."
    )

    if parameter_neighborhood is None:
        if overfitting.any_flag_raised:
            return CategoryScore("WEAK", overfitting_note + " Parameter neighborhood NOT evaluated.")
        return CategoryScore(
            "UNKNOWN", overfitting_note + " Parameter neighborhood NOT evaluated — cannot judge stability.",
        )

    pfs = [s.profit_factor for s in parameter_neighborhood if s.profit_factor is not None]
    if not pfs:
        return CategoryScore("UNKNOWN", "Parameter neighborhood provided but no profit_factor values available.")

    if overfitting.any_flag_raised:
        return CategoryScore("WEAK", overfitting_note + " Overfitting flag(s) raised, regardless of parameter neighborhood shape.")

    all_above_one = all(pf > 1.0 for pf in pfs)
    all_below_one = all(pf <= 1.0 for pf in pfs)

    if all_above_one:
        return CategoryScore("STRONG", "Every tested neighboring parameter value also shows profit factor > 1.0 — stable, not a lone peak.")
    if all_below_one:
        return CategoryScore("WEAK", "No tested parameter value (including neighbors) shows profit factor > 1.0.")
    return CategoryScore(
        "WEAK",
        "Parameter neighborhood is mixed — some values above 1.0, some not — consistent with a fragile, "
        "isolated result rather than a stable pattern (see e.g. Phase 8.1's H1 finding).",
    )


def _risk_score(out_of_sample: BacktestSummary, regime_dependence: Optional[dict]) -> CategoryScore:
    dd = out_of_sample.max_drawdown_percent
    avg_win = out_of_sample.average_win
    avg_loss = out_of_sample.average_loss
    payoff_ratio = (avg_win / abs(avg_loss)) if (avg_win and avg_loss) else None

    if dd is None or payoff_ratio is None:
        return CategoryScore("UNKNOWN", "Drawdown or payoff-ratio data unavailable from the out-of-sample summary.")

    reasons = [f"max_drawdown={dd:.1%}", f"payoff_ratio={payoff_ratio:.2f}"]

    if dd >= DRAWDOWN_WEAK_MIN or payoff_ratio <= PAYOFF_RATIO_WEAK_MAX:
        level = "WEAK"
    elif dd < DRAWDOWN_STRONG_MAX and payoff_ratio >= PAYOFF_RATIO_STRONG_MIN:
        level = "STRONG"
    else:
        level = "MODERATE"

    if regime_dependence is not None:
        positive_buckets = [k for k, v in regime_dependence.items() if v.get("net_pnl", 0) > 0]
        total_buckets = len(regime_dependence)
        if total_buckets > 0 and len(positive_buckets) <= 1 and total_buckets > 1:
            reasons.append(
                f"result concentrated in {len(positive_buckets)}/{total_buckets} regime bucket(s) — "
                "not broad-based"
            )
            if level == "STRONG":
                level = "MODERATE"
    else:
        reasons.append("regime dependence not evaluated")

    return CategoryScore(level, "; ".join(reasons) + ".")


def _statistical_score(statistical_evidence: Optional[dict]) -> CategoryScore:
    """
    Expects the same shape statistics_analysis.py produces: a dict with
    (at minimum) 'wilson_ci' (tuple) and 'bootstrap_ci_total_pnl' (tuple)
    and 'breakeven_win_rate' (float) and 'actual_win_rate' (float).
    """
    if statistical_evidence is None:
        return CategoryScore("UNKNOWN", "No statistical analysis (Wilson/bootstrap) has been run for this candidate.")

    wilson = statistical_evidence.get("wilson_ci")
    bootstrap = statistical_evidence.get("bootstrap_ci_total_pnl")
    breakeven = statistical_evidence.get("breakeven_win_rate")
    actual_wr = statistical_evidence.get("actual_win_rate")

    if wilson is None or bootstrap is None:
        return CategoryScore("UNKNOWN", "Statistical evidence dict provided but missing Wilson/bootstrap intervals.")

    wilson_excludes_breakeven_favorably = breakeven is not None and wilson[0] > breakeven
    bootstrap_excludes_zero_favorably = bootstrap[0] > 0

    if wilson_excludes_breakeven_favorably and bootstrap_excludes_zero_favorably:
        return CategoryScore(
            "STRONG",
            f"Wilson 95% CI ({wilson[0]:.3f}, {wilson[1]:.3f}) excludes the breakeven win rate "
            f"({breakeven:.3f}), and the bootstrap 95% P&L CI excludes zero.",
        )

    wilson_contains_breakeven = breakeven is not None and wilson[0] <= breakeven <= wilson[1]
    bootstrap_contains_zero = bootstrap[0] <= 0 <= bootstrap[1]

    if wilson_contains_breakeven and bootstrap_contains_zero:
        return CategoryScore(
            "WEAK",
            f"Actual win rate {actual_wr:.3f} is statistically indistinguishable from the breakeven rate "
            f"{breakeven:.3f} (Wilson CI contains it), and total P&L is statistically indistinguishable "
            "from zero (bootstrap CI contains zero).",
        )

    return CategoryScore("MODERATE", "Wilson and bootstrap intervals give mixed signals — not clearly distinguishable from chance, not clearly not.")


def _realism_score(
    out_of_sample_base_cost: BacktestSummary, cost_tier_summaries: Optional[dict]
) -> CategoryScore:
    if cost_tier_summaries is None:
        pf = out_of_sample_base_cost.profit_factor
        base_note = "Only a single (BASE) cost assumption evaluated — no LOW/HIGH cost sensitivity sweep run."
        if pf is not None and pf <= 1.0:
            return CategoryScore("WEAK", f"{base_note} Already fails at BASE cost (profit factor {pf:.3f}).")
        return CategoryScore("UNKNOWN", base_note)

    high = cost_tier_summaries.get("HIGH")
    base = cost_tier_summaries.get("BASE")
    if high is None or base is None:
        return CategoryScore("UNKNOWN", "Cost tier data incomplete — missing BASE or HIGH tier result.")

    high_pf = high.profit_factor
    base_pf = base.profit_factor

    if high_pf is not None and high_pf > 1.0:
        return CategoryScore("STRONG", f"Profit factor remains above 1.0 even at HIGH cost ({high_pf:.3f}).")
    if base_pf is not None and base_pf > 1.0:
        high_pf_str = f"{high_pf:.3f}" if high_pf is not None else "n/a"
        return CategoryScore(
            "MODERATE",
            f"Survives BASE cost (profit factor {base_pf:.3f}) but not HIGH cost ({high_pf_str}).",
        )
    return CategoryScore("WEAK", "Does not survive even BASE-cost trading assumptions.")


def compute_scorecard(
    period_summaries: dict,  # {"development": BacktestSummary, "validation": ..., "out_of_sample": ...}
    verdict: Verdict,
    overfitting: OverfittingDiagnostics,
    *,
    parameter_neighborhood: Optional[list[BacktestSummary]] = None,
    cost_tier_summaries: Optional[dict] = None,  # {"LOW": BacktestSummary, "BASE": ..., "HIGH": ...}
    statistical_evidence: Optional[dict] = None,
    regime_dependence: Optional[dict] = None,
) -> Scorecard:
    oos = period_summaries["out_of_sample"]

    return Scorecard(
        edge=_edge_score(verdict, oos),
        robustness=_robustness_score(verdict, overfitting, parameter_neighborhood),
        risk=_risk_score(oos, regime_dependence),
        statistical=_statistical_score(statistical_evidence),
        realism=_realism_score(oos, cost_tier_summaries),
        underlying_verdict=verdict.value,
    )
