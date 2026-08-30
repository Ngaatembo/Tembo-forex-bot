from app.strategy_engine.service import run_crossover_strategy
from tests.fixtures.technical_eurusd_candles import synthetic_eurusd_50_candles


def test_full_pipeline_produces_aligned_signals():
    candles = synthetic_eurusd_50_candles()
    signals = run_crossover_strategy(candles, symbol="EUR/USD")

    assert len(signals) == len(candles)
    for candle, signal in zip(candles, signals):
        assert signal.timestamp == candle.timestamp

    # warm-up period (first 49 candles, since SMA50 needs 50) must all be WAIT
    assert all(s.direction == "WAIT" for s in signals[:49])


def test_full_pipeline_never_produces_invalid_direction():
    candles = synthetic_eurusd_50_candles()
    signals = run_crossover_strategy(candles, symbol="EUR/USD")
    assert all(s.direction in ("BUY", "SELL", "WAIT") for s in signals)
