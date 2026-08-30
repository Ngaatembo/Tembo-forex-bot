import pytest
from datetime import datetime, timedelta, timezone

from app.backtesting.config import BacktestConfig
from app.backtesting.metrics import compute_metrics
from app.backtesting.models import Trade
from app.backtesting.portfolio import Portfolio

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def dummy_trade(trade_id: int, net_pnl: float) -> Trade:
    """Minimal trade with only net_pnl varying — everything else is a
    fixed placeholder, since win rate/profit factor only depend on net_pnl."""
    ts = BASE + timedelta(hours=trade_id)
    return Trade(
        trade_id=trade_id, symbol="EUR/USD", direction="LONG",
        signal_timestamp=ts, entry_timestamp=ts, entry_price=1.10,
        exit_timestamp=ts + timedelta(hours=1), exit_price=1.10, size=10_000,
        gross_pnl=net_pnl, transaction_costs=0.0, net_pnl=net_pnl,
        return_pct=net_pnl / (1.10 * 10_000), entry_reason="test", exit_reason="test",
    )


def test_win_rate_correct():
    """Test 12 — 3 wins, 1 loss -> 75% win rate."""
    trades = [dummy_trade(1, 100), dummy_trade(2, 80), dummy_trade(3, 60), dummy_trade(4, -50)]
    summary = compute_metrics(trades, [], initial_balance=1000)

    assert summary.trade_count == 4
    assert summary.winning_trades == 3
    assert summary.losing_trades == 1
    assert summary.win_rate == pytest.approx(0.75)


def test_profit_factor_correct():
    """Test 13 — profit_factor = gross_profit / abs(gross_loss)."""
    trades = [dummy_trade(1, 100), dummy_trade(2, 80), dummy_trade(3, 60), dummy_trade(4, -50)]
    summary = compute_metrics(trades, [], initial_balance=1000)

    expected = (100 + 80 + 60) / 50
    assert summary.profit_factor == pytest.approx(expected)


def test_profit_factor_is_none_with_zero_losses():
    """An 'infinite' profit factor is misleading — must report None, not inf."""
    trades = [dummy_trade(1, 100), dummy_trade(2, 50)]
    summary = compute_metrics(trades, [], initial_balance=1000)
    assert summary.profit_factor is None


def test_max_drawdown_computed_correctly_from_equity_sequence():
    """Test 14 — verified via Portfolio's own mark-to-market, not a
    hand-typed EquityPoint list, so the peak-tracking logic itself is tested."""
    config = BacktestConfig(spread=0.0, slippage=0.0, initial_balance=1000, position_size=10_000)
    portfolio = Portfolio(config)
    portfolio.open_position(
        direction="LONG", mid_price=1.1000, timestamp=BASE, signal_timestamp=BASE, reason="test"
    )

    p1 = portfolio.mark_to_market(mid_price=1.1010, timestamp=BASE + timedelta(hours=1))  # equity 1010, new peak
    p2 = portfolio.mark_to_market(mid_price=1.0990, timestamp=BASE + timedelta(hours=2))  # equity 990, dd from peak 1010
    p3 = portfolio.mark_to_market(mid_price=1.1030, timestamp=BASE + timedelta(hours=3))  # equity 1030, new peak, dd 0

    assert p1.drawdown == pytest.approx(0.0)
    assert p2.drawdown == pytest.approx(20.0)
    assert p2.drawdown_percent == pytest.approx(20.0 / 1010.0)
    assert p3.drawdown == pytest.approx(0.0)

    summary = compute_metrics([], [p1, p2, p3], initial_balance=1000)
    assert summary.max_drawdown == pytest.approx(20.0)


def test_no_trade_dataset_produces_safe_metrics():
    """Test 16 — zero trades must never crash or fabricate a ratio."""
    summary = compute_metrics([], [], initial_balance=1000)

    assert summary.trade_count == 0
    assert summary.net_pnl == 0
    assert summary.final_balance == 1000
    assert summary.win_rate is None
    assert summary.profit_factor is None
    assert summary.average_win is None
    assert summary.average_loss is None
    assert summary.max_consecutive_wins is None
