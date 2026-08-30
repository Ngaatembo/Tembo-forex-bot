from app.backtesting.models import BacktestSummary
from app.research.verdict import Verdict, compute_verdict


def summary(trade_count=50, profit_factor=1.2, total_return=0.1) -> BacktestSummary:
    return BacktestSummary(
        initial_balance=10000.0, final_balance=10000.0 * (1 + total_return),
        net_pnl=10000.0 * total_return, total_return=total_return, trade_count=trade_count,
        profit_factor=profit_factor,
    )


def test_inconclusive_when_any_period_has_too_few_trades():
    verdict = compute_verdict(
        development=summary(trade_count=5), validation=summary(), out_of_sample=summary(),
    )
    assert verdict == Verdict.INCONCLUSIVE


def test_rejected_when_development_itself_fails():
    verdict = compute_verdict(
        development=summary(profit_factor=0.8), validation=summary(), out_of_sample=summary(),
    )
    assert verdict == Verdict.REJECTED


def test_out_of_sample_failed_when_dev_works_but_oos_does_not():
    verdict = compute_verdict(
        development=summary(profit_factor=1.5), validation=summary(profit_factor=1.3),
        out_of_sample=summary(profit_factor=0.9),
    )
    assert verdict == Verdict.OUT_OF_SAMPLE_FAILED


def test_overfit_suspected_when_validation_fails_despite_dev_and_oos_working():
    verdict = compute_verdict(
        development=summary(profit_factor=1.5), validation=summary(profit_factor=0.9),
        out_of_sample=summary(profit_factor=1.4),
    )
    assert verdict == Verdict.OVERFIT_SUSPECTED


def test_overfit_suspected_when_oos_degrades_heavily_even_if_still_above_one():
    # dev pf=2.0, oos pf=1.05 -> degradation = (2.0-1.05)/2.0 = 0.475... need >0.5, adjust
    verdict = compute_verdict(
        development=summary(profit_factor=3.0), validation=summary(profit_factor=1.3),
        out_of_sample=summary(profit_factor=1.2),  # degradation = (3.0-1.2)/3.0 = 0.6 > 0.5
    )
    assert verdict == Verdict.OVERFIT_SUSPECTED


def test_promising_when_consistent_across_all_periods():
    verdict = compute_verdict(
        development=summary(profit_factor=1.3), validation=summary(profit_factor=1.25),
        out_of_sample=summary(profit_factor=1.2),
    )
    assert verdict == Verdict.PROMISING


def test_validated_for_paper_trading_is_never_auto_assigned():
    """Even a perfect-looking result across all three periods must not
    auto-grant this status — it's reserved for a separate human/process
    decision, per the verdict engine's explicit design."""
    verdict = compute_verdict(
        development=summary(profit_factor=5.0, trade_count=1000),
        validation=summary(profit_factor=5.0, trade_count=1000),
        out_of_sample=summary(profit_factor=5.0, trade_count=1000),
    )
    assert verdict != Verdict.VALIDATED_FOR_PAPER_TRADING
    assert verdict == Verdict.PROMISING


def test_high_return_alone_cannot_produce_promising_if_pf_below_one():
    """A summary could theoretically have positive return with pf<=1 in
    edge cases — the verdict must key off profit_factor, not return."""
    verdict = compute_verdict(
        development=summary(profit_factor=0.99, total_return=0.5),
        validation=summary(), out_of_sample=summary(),
    )
    assert verdict == Verdict.REJECTED
