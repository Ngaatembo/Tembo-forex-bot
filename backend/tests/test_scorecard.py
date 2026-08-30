from app.backtesting.models import BacktestSummary
from app.research.overfitting import compute_overfitting_diagnostics
from app.research.scorecard import compute_scorecard
from app.research.verdict import Verdict, compute_verdict


def summary(**overrides) -> BacktestSummary:
    defaults = dict(
        initial_balance=10000.0, final_balance=10000.0, net_pnl=0.0, total_return=0.0,
        trade_count=100, winning_trades=50, losing_trades=50, win_rate=0.5,
        average_win=100.0, average_loss=-100.0, largest_win=200.0, largest_loss=-200.0,
        average_trade=0.0, expectancy=0.0, max_consecutive_wins=5, max_consecutive_losses=5,
        profit_factor=1.0, max_drawdown=1000.0, max_drawdown_percent=0.10,
    )
    defaults.update(overrides)
    return BacktestSummary(**defaults)


def three_periods(**shared_overrides):
    """Convenience: build dev/val/oos with the same shape unless overridden per-call."""
    return {
        "development": summary(**shared_overrides),
        "validation": summary(**shared_overrides),
        "out_of_sample": summary(**shared_overrides),
    }


def test_clearly_negative_experiment_scores_weak():
    """Consistent with the actual SMA10/50 baseline: profit_factor < 1.0 everywhere."""
    periods = three_periods(profit_factor=0.85, trade_count=500)
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting)

    assert verdict == Verdict.REJECTED
    assert card.edge.level == "WEAK"


def test_genuinely_promising_evidence_scores_strong_edge():
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=100),
        "out_of_sample": summary(profit_factor=1.15, trade_count=200),
    }
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting)

    assert verdict == Verdict.PROMISING
    assert card.edge.level == "STRONG"


def test_oos_failure_overrides_strong_development_edge():
    """Critical safeguard: a great development result must NOT produce a strong EDGE if OOS failed."""
    periods = {
        "development": summary(profit_factor=1.8, trade_count=500),  # looks great
        "validation": summary(profit_factor=1.3, trade_count=100),
        "out_of_sample": summary(profit_factor=0.7, trade_count=200),  # failed
    }
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting)

    assert verdict == Verdict.OUT_OF_SAMPLE_FAILED
    assert card.edge.level == "WEAK"  # NOT strong, despite the 1.8 development number


def test_h1_like_exact_breakeven_oos_scores_weak_edge_not_strong():
    """Mirrors H1's real Phase 8 result: dev/val fine, OOS exactly 1.000 -> OUT_OF_SAMPLE_FAILED, EDGE weak."""
    periods = {
        "development": summary(profit_factor=1.134, trade_count=681),
        "validation": summary(profit_factor=1.101, trade_count=199),
        "out_of_sample": summary(profit_factor=1.000, trade_count=253),
    }
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting)

    assert verdict == Verdict.OUT_OF_SAMPLE_FAILED
    assert card.edge.level == "WEAK"
    assert "0.95" not in card.edge.reason or "1.000" in card.edge.reason or "close to breakeven" in card.edge.reason


def test_missing_robustness_evidence_is_unknown_not_strong():
    """No parameter_neighborhood provided -> ROBUSTNESS is UNKNOWN (missing
    evidence is never assumed positive), never STRONG."""
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=100),
        "out_of_sample": summary(profit_factor=1.15, trade_count=200),
    }
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting)  # no parameter_neighborhood passed

    assert card.robustness.level != "STRONG"
    assert "not evaluated" in card.robustness.reason.lower() or "not been run" in card.robustness.reason.lower()


def test_parameter_neighborhood_fragile_isolated_peak_scores_weak():
    """Mirrors Phase 8.1's real H1 finding: a lone peak at the chosen value, worse on both sides."""
    periods = {
        "development": summary(profit_factor=1.134, trade_count=681),
        "validation": summary(profit_factor=1.101, trade_count=199),
        "out_of_sample": summary(profit_factor=1.001, trade_count=253),  # just above 1.0 to reach PROMISING
    }
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    neighborhood = [
        summary(profit_factor=0.902, trade_count=221),  # neighbor below
        summary(profit_factor=1.001, trade_count=253),  # chosen value
        summary(profit_factor=0.927, trade_count=253),  # neighbor below
    ]
    card = compute_scorecard(periods, verdict, overfitting, parameter_neighborhood=neighborhood)

    assert card.robustness.level == "WEAK"
    assert "fragile" in card.robustness.reason.lower() or "isolated" in card.robustness.reason.lower()


def test_poor_payoff_ratio_despite_high_win_rate_is_not_strong_risk():
    """Mirrors H1's real out-of-sample numbers: 66% win rate but avg_win $26 / avg_loss -$53 (ratio ~0.5)."""
    oos = summary(win_rate=0.664, average_win=26.43, average_loss=-52.88, max_drawdown_percent=0.14)
    periods = {"development": oos, "validation": oos, "out_of_sample": oos}
    card = compute_scorecard(
        periods, Verdict.OUT_OF_SAMPLE_FAILED, compute_overfitting_diagnostics(**periods)
    )
    assert card.risk.level in ("WEAK", "MODERATE")
    assert card.risk.level != "STRONG"
    assert "payoff_ratio" in card.risk.reason


def test_high_drawdown_scores_weak_risk():
    oos = summary(max_drawdown_percent=0.55, average_win=200.0, average_loss=-100.0)
    periods = {"development": oos, "validation": oos, "out_of_sample": oos}
    card = compute_scorecard(periods, Verdict.PROMISING, compute_overfitting_diagnostics(**periods))
    assert card.risk.level == "WEAK"


def test_regime_concentration_downgrades_strong_risk_to_moderate():
    oos = summary(max_drawdown_percent=0.05, average_win=300.0, average_loss=-100.0)
    periods = {"development": oos, "validation": oos, "out_of_sample": oos}
    regime_dependence = {
        "RANGING": {"net_pnl": -100.0}, "TRENDING_UP": {"net_pnl": 500.0}, "TRENDING_DOWN": {"net_pnl": -50.0},
    }
    card = compute_scorecard(
        periods, Verdict.PROMISING, compute_overfitting_diagnostics(**periods), regime_dependence=regime_dependence
    )
    assert card.risk.level == "MODERATE"
    assert "concentrated" in card.risk.reason


def test_weak_statistical_evidence_mirrors_h1_finding():
    """Mirrors Phase 8.1's real H1 statistical result: both CIs contain the null."""
    periods = three_periods(profit_factor=1.0, trade_count=253)
    statistical_evidence = {
        "wilson_ci": (0.6038, 0.7194), "breakeven_win_rate": 0.6667,
        "bootstrap_ci_total_pnl": (-1714.0, 1596.8), "actual_win_rate": 0.664,
    }
    card = compute_scorecard(
        periods, Verdict.OUT_OF_SAMPLE_FAILED, compute_overfitting_diagnostics(**periods),
        statistical_evidence=statistical_evidence,
    )
    assert card.statistical.level == "WEAK"
    assert "indistinguishable" in card.statistical.reason.lower()


def test_missing_statistical_evidence_is_unknown_not_assumed_positive():
    periods = three_periods(profit_factor=1.2, trade_count=200)
    card = compute_scorecard(periods, Verdict.PROMISING, compute_overfitting_diagnostics(**periods))
    assert card.statistical.level == "UNKNOWN"


def test_strong_cost_sensitivity_downgrades_realism():
    """Mirrors real project findings: an edge that vanishes at HIGH cost."""
    periods = three_periods(profit_factor=1.1, trade_count=200)
    cost_tiers = {
        "LOW": summary(profit_factor=1.15), "BASE": summary(profit_factor=1.05), "HIGH": summary(profit_factor=0.92),
    }
    card = compute_scorecard(
        periods, Verdict.PROMISING, compute_overfitting_diagnostics(**periods), cost_tier_summaries=cost_tiers,
    )
    assert card.realism.level == "MODERATE"
    assert "HIGH cost" in card.realism.reason


def test_survives_high_cost_scores_strong_realism():
    periods = three_periods(profit_factor=1.1, trade_count=200)
    cost_tiers = {
        "LOW": summary(profit_factor=1.2), "BASE": summary(profit_factor=1.1), "HIGH": summary(profit_factor=1.02),
    }
    card = compute_scorecard(
        periods, Verdict.PROMISING, compute_overfitting_diagnostics(**periods), cost_tier_summaries=cost_tiers,
    )
    assert card.realism.level == "STRONG"


def test_missing_cost_tier_data_falls_back_to_base_only_check():
    periods = three_periods(profit_factor=0.9, trade_count=200)
    card = compute_scorecard(periods, Verdict.REJECTED, compute_overfitting_diagnostics(**periods))
    assert card.realism.level == "WEAK"  # already fails at the one cost tier we do have


def test_serialization_to_dict():
    periods = three_periods(profit_factor=1.2, trade_count=200)
    card = compute_scorecard(periods, Verdict.PROMISING, compute_overfitting_diagnostics(**periods))
    d = card.to_dict()
    assert d["edge"]["level"] == "STRONG"
    assert d["underlying_verdict"] == "PROMISING"


def test_deterministic_output_same_inputs_same_result():
    periods = three_periods(profit_factor=1.1, trade_count=150)
    overfitting = compute_overfitting_diagnostics(**periods)
    first = compute_scorecard(periods, Verdict.PROMISING, overfitting)
    second = compute_scorecard(periods, Verdict.PROMISING, overfitting)
    assert first == second
