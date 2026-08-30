"""
Convenience entrypoint chaining technical_engine -> strategy_engine.

This is the only place that imports both engines together — neither
engine imports the other directly, which is what keeps them
independently testable and independently swappable (e.g. adding a
second strategy later doesn't touch technical_engine at all).
"""

from app.data_engine.market_data import Candle
from app.strategy_engine.crossover import detect_crossover_signals
from app.strategy_engine.models import Signal
from app.technical_engine.service import calculate_features


def run_crossover_strategy(candles: list[Candle], symbol: str) -> list[Signal]:
    features = calculate_features(candles)
    return detect_crossover_signals(features, symbol=symbol)
