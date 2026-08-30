from app.backtesting.models import BacktestSummary
from app.research.overfitting import compute_overfitting_diagnostics


def summary(trade_count=50, profit_factor=1.2, total_return=0.1) -> BacktestSummary:
    return BacktestSummary(
        initial_balance=10000.0, final_balance=10000.0 * (1 + total_return),
        net_pnl=10000.0 * total_return, total_return=total_return, trade_count=trade_count,
        profit_factor=profit_factor,
    )


def test_low_trade_count_flagged_per_period():
    diag = compute_overfitting_diagnostics(
        development=summary(trade_count=5), validation=summary(trade_count=50), out_of_sample=summary(trade_count=50)
    )
    assert diag.low_trade_count_development is True
    assert diag.low_trade_count_validation is False
    assert diag.any_flag_raised is True


def test_strong_dev_then_oos_failure_flagged():
    diag = compute_overfitting_diagnostics(
        development=summary(profit_factor=1.5), validation=summary(profit_factor=1.3),
        out_of_sample=summary(profit_factor=0.8),
    )
    assert diag.strong_dev_then_oos_failure is True
    assert diag.any_flag_raised is True


def test_clean_consistent_result_raises_no_flags():
    diag = compute_overfitting_diagnostics(
        development=summary(profit_factor=1.2, trade_count=100),
        validation=summary(profit_factor=1.18, trade_count=100),
        out_of_sample=summary(profit_factor=1.15, trade_count=100),
    )
    assert diag.any_flag_raised is False


def test_degradation_computed_correctly():
    diag = compute_overfitting_diagnostics(
        development=summary(profit_factor=2.0), validation=summary(profit_factor=1.5),
        out_of_sample=summary(profit_factor=1.0),
    )
    assert diag.development_to_oos_pf_degradation == 0.5


def test_returns_captured_for_all_three_periods():
    diag = compute_overfitting_diagnostics(
        development=summary(total_return=0.3), validation=summary(total_return=0.05),
        out_of_sample=summary(total_return=-0.1),
    )
    assert diag.development_return == 0.3
    assert diag.validation_return == 0.05
    assert diag.out_of_sample_return == -0.1
