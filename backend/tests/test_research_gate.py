from app.backtesting.models import BacktestSummary
from app.research.overfitting import compute_overfitting_diagnostics
from app.research.research_gate import compute_research_gate
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


def gate_for(periods, **scorecard_kwargs):
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting, **scorecard_kwargs)
    return compute_research_gate(verdict, card, overfitting), verdict, card, overfitting


def test_1_strong_development_failed_oos_is_blocked():
    """Strong dev + failed OOS must NEVER reach PROMISING or PAPER_CANDIDATE."""
    periods = {
        "development": summary(profit_factor=1.8, trade_count=500),
        "validation": summary(profit_factor=1.3, trade_count=100),
        "out_of_sample": summary(profit_factor=0.7, trade_count=200),
    }
    result, verdict, _, _ = gate_for(periods)
    assert verdict == Verdict.OUT_OF_SAMPLE_FAILED
    assert result.status not in ("PROMISING", "PAPER_CANDIDATE")
    assert result.status == "CLOSED"


def test_2_oos_failure_cannot_become_promising_even_with_other_strong_evidence():
    periods = {
        "development": summary(profit_factor=1.5, trade_count=500),
        "validation": summary(profit_factor=1.4, trade_count=200),
        "out_of_sample": summary(profit_factor=0.9, trade_count=300),
    }
    neighborhood = [summary(profit_factor=1.4), summary(profit_factor=1.5), summary(profit_factor=1.6)]
    stats = {
        "wilson_ci": (0.6, 0.7), "breakeven_win_rate": 0.4,
        "bootstrap_ci_total_pnl": (100.0, 500.0), "actual_win_rate": 0.65,
    }
    result, verdict, _, _ = gate_for(
        periods, parameter_neighborhood=neighborhood, statistical_evidence=stats,
    )
    assert verdict == Verdict.OUT_OF_SAMPLE_FAILED
    assert result.status not in ("PROMISING", "PAPER_CANDIDATE")


def test_3_missing_robustness_evidence_yields_robustness_required():
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=100),
        "out_of_sample": summary(profit_factor=1.15, trade_count=200),
    }
    result, verdict, _, _ = gate_for(periods)  # no parameter_neighborhood
    assert verdict == Verdict.PROMISING
    assert result.status == "ROBUSTNESS_REQUIRED"


def test_4_overfitting_flag_blocks_advancement():
    periods = {
        "development": summary(profit_factor=1.5, trade_count=15),  # low trade count -> triggers overfitting flag
        "validation": summary(profit_factor=1.4, trade_count=200),
        "out_of_sample": summary(profit_factor=1.3, trade_count=200),
    }
    result, verdict, card, overfitting = gate_for(periods)
    assert overfitting.any_flag_raised is True
    assert result.status == "ROBUSTNESS_REQUIRED"
    assert result.status not in ("PROMISING", "PAPER_CANDIDATE")


def test_5_good_oos_and_robust_evidence_reaches_promising():
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=200),
        "out_of_sample": summary(profit_factor=1.15, trade_count=300),
    }
    neighborhood = [summary(profit_factor=1.1), summary(profit_factor=1.2), summary(profit_factor=1.3)]
    result, verdict, _, _ = gate_for(periods, parameter_neighborhood=neighborhood)
    assert verdict == Verdict.PROMISING
    assert result.status in ("PROMISING", "PAPER_CANDIDATE")


def test_6_even_strongest_possible_evidence_never_authorizes_trading():
    """PAPER_CANDIDATE is the ceiling — its own reason text must explicitly
    disclaim trading authorization, and the gate module has no execution path at all."""
    periods = {
        "development": summary(profit_factor=1.5, trade_count=1000, max_drawdown_percent=0.05,
                                average_win=300.0, average_loss=-100.0),
        "validation": summary(profit_factor=1.4, trade_count=500, max_drawdown_percent=0.05,
                               average_win=300.0, average_loss=-100.0),
        "out_of_sample": summary(profit_factor=1.3, trade_count=500, max_drawdown_percent=0.05,
                                  average_win=300.0, average_loss=-100.0),
    }
    neighborhood = [summary(profit_factor=1.2), summary(profit_factor=1.3), summary(profit_factor=1.4)]
    cost_tiers = {"LOW": summary(profit_factor=1.4), "BASE": summary(profit_factor=1.3), "HIGH": summary(profit_factor=1.15)}
    stats = {
        "wilson_ci": (0.55, 0.65), "breakeven_win_rate": 0.35,
        "bootstrap_ci_total_pnl": (1000.0, 5000.0), "actual_win_rate": 0.6,
    }
    result, verdict, card, _ = gate_for(
        periods, parameter_neighborhood=neighborhood, cost_tier_summaries=cost_tiers, statistical_evidence=stats,
    )
    assert result.status == "PAPER_CANDIDATE"
    assert "does not" in result.reason.lower() or "does NOT" in result.reason
    assert "start paper trading" in result.reason or "authorize" in result.reason.lower()
    # Structural guarantee: no import of execution anywhere in this module (see security test too)
    import app.research.research_gate as rg
    assert not hasattr(rg, "place_order")
    assert not hasattr(rg, "broker_adapter")


def test_7_high_win_rate_poor_payoff_ratio_blocked_at_robustness_required():
    """Mirrors H1's real shape: decent win rate, poor payoff ratio -> risk WEAK -> blocked."""
    oos = summary(win_rate=0.664, average_win=26.43, average_loss=-52.88, max_drawdown_percent=0.14, profit_factor=1.05, trade_count=253)
    periods = {"development": summary(profit_factor=1.13, trade_count=681),
               "validation": summary(profit_factor=1.10, trade_count=199), "out_of_sample": oos}
    neighborhood = [summary(profit_factor=1.05), summary(profit_factor=1.1), summary(profit_factor=1.13)]
    result, verdict, card, _ = gate_for(periods, parameter_neighborhood=neighborhood)
    assert card.risk.level == "WEAK"
    assert result.status == "ROBUSTNESS_REQUIRED"
    assert result.status not in ("PROMISING", "PAPER_CANDIDATE")


def test_8_missing_statistics_and_cost_evidence_stays_conservative():
    """Robustness/risk fine, but no statistical or cost-tier data -> can reach
    PROMISING at most, never PAPER_CANDIDATE (which requires STRONG statistical)."""
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500, average_win=300, average_loss=-100, max_drawdown_percent=0.1),
        "validation": summary(profit_factor=1.2, trade_count=200, average_win=300, average_loss=-100, max_drawdown_percent=0.1),
        "out_of_sample": summary(profit_factor=1.15, trade_count=300, average_win=300, average_loss=-100, max_drawdown_percent=0.1),
    }
    neighborhood = [summary(profit_factor=1.1), summary(profit_factor=1.15), summary(profit_factor=1.2)]
    result, verdict, card, _ = gate_for(periods, parameter_neighborhood=neighborhood)
    assert card.statistical.level == "UNKNOWN"
    assert result.status != "PAPER_CANDIDATE"


def test_9_deterministic_repeated_evaluation():
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=200),
        "out_of_sample": summary(profit_factor=1.15, trade_count=300),
    }
    verdict = compute_verdict(**periods)
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, verdict, overfitting)
    first = compute_research_gate(verdict, card, overfitting)
    second = compute_research_gate(verdict, card, overfitting)
    assert first == second


def test_10_serialization():
    periods = {
        "development": summary(profit_factor=0.8, trade_count=500),
        "validation": summary(profit_factor=0.9, trade_count=200),
        "out_of_sample": summary(profit_factor=0.7, trade_count=300),
    }
    result, _, _, _ = gate_for(periods)
    d = result.to_dict()
    assert d["status"] == "REJECT_EARLY"
    assert "reason" in d and "evidence_used" in d


def test_reject_early_vs_closed_distinction():
    """REJECTED (dev never worked) -> REJECT_EARLY. OUT_OF_SAMPLE_FAILED
    (full pipeline ran, oos specifically failed) -> CLOSED. Different labels."""
    rejected_periods = {
        "development": summary(profit_factor=0.8, trade_count=500),
        "validation": summary(profit_factor=0.9, trade_count=200),
        "out_of_sample": summary(profit_factor=0.85, trade_count=300),
    }
    oos_failed_periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=200),
        "out_of_sample": summary(profit_factor=0.9, trade_count=300),
    }
    r1, v1, _, _ = gate_for(rejected_periods)
    r2, v2, _, _ = gate_for(oos_failed_periods)
    assert v1 == Verdict.REJECTED and r1.status == "REJECT_EARLY"
    assert v2 == Verdict.OUT_OF_SAMPLE_FAILED and r2.status == "CLOSED"


def test_inconclusive_maps_to_research():
    periods = {
        "development": summary(profit_factor=1.2, trade_count=5),
        "validation": summary(profit_factor=1.1, trade_count=5),
        "out_of_sample": summary(profit_factor=1.0, trade_count=5),
    }
    result, verdict, _, _ = gate_for(periods)
    assert verdict == Verdict.INCONCLUSIVE
    assert result.status == "RESEARCH"


def test_overfit_suspected_maps_to_robustness_required():
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=0.9, trade_count=200),  # fails validation specifically
        "out_of_sample": summary(profit_factor=1.2, trade_count=300),
    }
    result, verdict, _, _ = gate_for(periods)
    assert verdict == Verdict.OVERFIT_SUSPECTED
    assert result.status == "ROBUSTNESS_REQUIRED"


def test_validated_for_paper_trading_verdict_never_treated_as_permission():
    """Defensive test: even if a Verdict of VALIDATED_FOR_PAPER_TRADING were
    ever passed in (compute_verdict itself never returns it), the gate must
    handle it via the same evidence-based path as PROMISING, never a shortcut."""
    periods = {
        "development": summary(profit_factor=1.3, trade_count=500),
        "validation": summary(profit_factor=1.2, trade_count=200),
        "out_of_sample": summary(profit_factor=1.15, trade_count=300),
    }
    overfitting = compute_overfitting_diagnostics(**periods)
    card = compute_scorecard(periods, Verdict.VALIDATED_FOR_PAPER_TRADING, overfitting)
    result = compute_research_gate(Verdict.VALIDATED_FOR_PAPER_TRADING, card, overfitting)
    # No parameter_neighborhood was given, so this must still be blocked at
    # ROBUSTNESS_REQUIRED -- proving the verdict label alone grants nothing.
    assert result.status == "ROBUSTNESS_REQUIRED"
