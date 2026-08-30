import pytest
from datetime import datetime, timedelta, timezone

from app.backtesting.models import Trade
from app.research.statistics_analysis import (
    bootstrap_pnl_confidence_interval, compute_breakeven_win_rate,
    compute_payoff_stats, wilson_confidence_interval,
)

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def make_trade(net_pnl: float) -> Trade:
    ts = BASE
    return Trade(
        trade_id=1, symbol="EUR/USD", direction="LONG", signal_timestamp=ts,
        entry_timestamp=ts, entry_price=1.10, exit_timestamp=ts + timedelta(hours=1),
        exit_price=1.10, size=10_000, gross_pnl=net_pnl, transaction_costs=0.0,
        net_pnl=net_pnl, return_pct=net_pnl / (1.10 * 10_000), entry_reason="t", exit_reason="t",
    )


def test_payoff_stats_hand_verified():
    trades = [make_trade(100), make_trade(50), make_trade(-40), make_trade(-20)]
    stats = compute_payoff_stats(trades)
    assert stats.average_win == pytest.approx(75.0)  # (100+50)/2
    assert stats.average_loss == pytest.approx(-30.0)  # (-40-20)/2
    assert stats.largest_win == 100
    assert stats.largest_loss == -40
    assert stats.payoff_ratio == pytest.approx(2.5)  # 75/30


def test_payoff_stats_no_losses_returns_none_ratio():
    trades = [make_trade(100), make_trade(50)]
    stats = compute_payoff_stats(trades)
    assert stats.average_loss is None
    assert stats.payoff_ratio is None


def test_payoff_stats_empty_trades():
    stats = compute_payoff_stats([])
    assert stats.average_win is None
    assert stats.payoff_ratio is None


def test_breakeven_win_rate_hand_verified():
    # payoff_ratio 2.5 -> breakeven = 1/(1+2.5) = 0.2857...
    assert compute_breakeven_win_rate(2.5) == pytest.approx(1 / 3.5)
    # payoff_ratio 1.0 (symmetric win/loss) -> breakeven = 50%
    assert compute_breakeven_win_rate(1.0) == pytest.approx(0.5)


def test_breakeven_win_rate_none_when_undefined():
    assert compute_breakeven_win_rate(None) is None
    assert compute_breakeven_win_rate(0) is None


def test_wilson_interval_matches_known_reference_values():
    # 60 wins out of 100 -> point estimate 0.60; Wilson interval should
    # bracket 0.60 and be roughly [0.50, 0.69] at 95% confidence
    # (standard reference range for n=100, p=0.6).
    low, high = wilson_confidence_interval(60, 100)
    assert low < 0.60 < high
    assert 0.49 < low < 0.51
    assert 0.68 < high < 0.70


def test_wilson_interval_narrows_with_more_data():
    low_small, high_small = wilson_confidence_interval(60, 100)
    low_large, high_large = wilson_confidence_interval(600, 1000)
    assert (high_large - low_large) < (high_small - low_small)


def test_wilson_interval_zero_n_returns_none():
    assert wilson_confidence_interval(0, 0) is None


def test_wilson_interval_rejects_unsupported_confidence():
    with pytest.raises(NotImplementedError):
        wilson_confidence_interval(60, 100, confidence=0.99)


def test_bootstrap_interval_is_deterministic_given_fixed_seed():
    pnls = [100.0, -50.0, 80.0, -30.0, 60.0, -20.0]
    first = bootstrap_pnl_confidence_interval(pnls, n_resamples=1000, seed=42)
    second = bootstrap_pnl_confidence_interval(pnls, n_resamples=1000, seed=42)
    assert first == second


def test_bootstrap_resampling_is_genuinely_randomized_per_seed():
    """
    With only a handful of distinct input P&L values, the *boundary
    values* of the confidence interval can coincidentally match across
    different seeds (the resampled sums only take a small number of
    distinct discrete values) — this was verified NOT to be a bug: the
    full underlying resampled-totals lists differ per seed even when
    their 2.5th/97.5th percentile boundary happens to land on the same
    value. This test checks the real invariant (the underlying
    resampling differs) with a large enough varied sample that
    coincidental boundary matches are not plausible.
    """
    pnls = [float(i) * 1.37 - 5 for i in range(50)]  # 50 distinct, non-round values
    a = bootstrap_pnl_confidence_interval(pnls, n_resamples=2000, seed=1)
    b = bootstrap_pnl_confidence_interval(pnls, n_resamples=2000, seed=2)
    assert a != b
    true_sum = sum(pnls)
    assert a[0] < true_sum < a[1]
    assert b[0] < true_sum < b[1]


def test_bootstrap_interval_empty_returns_none():
    assert bootstrap_pnl_confidence_interval([]) is None


def test_bootstrap_interval_all_positive_never_includes_negative():
    pnls = [10.0, 20.0, 15.0, 25.0, 30.0]
    low, high = bootstrap_pnl_confidence_interval(pnls, n_resamples=2000, seed=7)
    assert low > 0  # resampling only positive values can never sum negative
