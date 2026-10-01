from app.backtesting.config import BacktestConfig
from app.backtesting.portfolio import Portfolio

def test_trigger_exit_costs_are_optional_and_applied_when_enabled():
    base = BacktestConfig(position_size=10_000, spread=0.20, slippage=0.05, initial_balance=10_000)
    priced = BacktestConfig(position_size=10_000, spread=0.20, slippage=0.05, initial_balance=10_000, apply_costs_to_trigger_exits=True)

    p1 = Portfolio(base)
    p1.open_position(direction="LONG", mid_price=100.0, timestamp=__import__("datetime").datetime.now(),
                     signal_timestamp=__import__("datetime").datetime.now(), reason="test",
                     stop_price=99.0)
    t1 = p1.close_position_at_price(exact_price=99.0, timestamp=__import__("datetime").datetime.now(), reason="STOP")

    p2 = Portfolio(priced)
    p2.open_position(direction="LONG", mid_price=100.0, timestamp=__import__("datetime").datetime.now(),
                     signal_timestamp=__import__("datetime").datetime.now(), reason="test",
                     stop_price=99.0)
    t2 = p2.close_position_at_price(exact_price=99.0, timestamp=__import__("datetime").datetime.now(), reason="STOP", apply_costs=True)

    assert t2.net_pnl < t1.net_pnl
    assert t2.transaction_costs > t1.transaction_costs
