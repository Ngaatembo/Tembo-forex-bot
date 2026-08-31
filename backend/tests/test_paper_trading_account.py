import pytest

from app.paper_trading.account import PaperAccountState
from app.paper_trading.models import PaperPosition
from datetime import datetime, timezone

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_position(instrument="XAU/USD", timeframe="h1", direction="LONG", entry=1900.0, stop=1880.0, size=5.0):
    return PaperPosition(
        position_id=f"pos_{instrument}_{timeframe}", instrument=instrument, timeframe=timeframe,
        direction=direction, entry_price=entry, entry_time=NOW, stop_price=stop, position_size=size,
        candidate_config_id="vsc_test",
    )


def test_initial_equity():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    assert account.equity({}) == 10000.0


def test_equity_reflects_unrealized_pnl():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(), risk_amount=100.0)
    equity = account.equity({"XAU/USD:h1": 1910.0})
    assert equity == pytest.approx(10050.0)


def test_equity_reflects_realized_pnl_after_close():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(), risk_amount=100.0)
    trade = account.close_position("XAU/USD:h1", exit_price=1920.0, exit_time=NOW, exit_reason="TAKE_PROFIT")
    assert trade.realized_pnl == pytest.approx(100.0)
    assert account.equity({}) == pytest.approx(10100.0)
    assert len(account.open_positions) == 0
    assert len(account.closed_trades) == 1


def test_available_equity_after_open_position():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(), risk_amount=100.0)
    assert account.total_open_risk_amount() == pytest.approx(100.0)


def test_drawdown_tracks_peak_equity():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(), risk_amount=100.0)
    dd = account.current_drawdown_pct({"XAU/USD:h1": 1880.0})
    assert dd == pytest.approx(100.0 / 10000.0)


def test_drawdown_zero_when_at_peak():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    assert account.current_drawdown_pct({}) == 0.0


def test_multiple_simultaneous_positions_different_instruments():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(instrument="XAU/USD", timeframe="h1"), risk_amount=100.0)
    account.open_position(make_position(instrument="EUR/USD", timeframe="m15", entry=1.10, stop=1.095, size=1000.0), risk_amount=50.0)
    assert len(account.open_positions) == 2
    assert account.total_open_risk_amount() == pytest.approx(150.0)


def test_duplicate_position_protection():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(), risk_amount=100.0)
    with pytest.raises(ValueError):
        account.open_position(make_position(), risk_amount=100.0)


def test_position_lookup_by_key():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    pos = make_position()
    account.open_position(pos, risk_amount=100.0)
    assert account.get_position("XAU/USD:h1") is pos


def test_close_nonexistent_position_raises():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    with pytest.raises(KeyError):
        account.close_position("NONEXISTENT:h1", exit_price=1.0, exit_time=NOW, exit_reason="TAKE_PROFIT")


def test_short_position_pnl_direction():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(direction="SHORT", entry=1900.0, stop=1920.0), risk_amount=100.0)
    trade = account.close_position("XAU/USD:h1", exit_price=1880.0, exit_time=NOW, exit_reason="TAKE_PROFIT")
    assert trade.realized_pnl == pytest.approx(100.0)


def test_to_risk_engine_account_state_snapshot():
    from app.risk_engine.risk_models import AccountState as RiskAccountState
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    account.open_position(make_position(), risk_amount=100.0)
    snapshot = account.to_risk_engine_snapshot(current_prices={"XAU/USD:h1": 1900.0})
    assert isinstance(snapshot, RiskAccountState)
    assert snapshot.equity == pytest.approx(10000.0)
    assert snapshot.open_positions_count == 1
    assert snapshot.total_open_risk_pct == pytest.approx(0.01)
