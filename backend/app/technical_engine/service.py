"""
calculate_features(candles) — the technical engine's public entrypoint.

Architectural boundary (see docs/architecture.md and phase-2-notes.md):
this module NEVER fetches data, never touches OANDA or PostgreSQL, and
never generates a trading signal. It receives already-validated,
already-normalized candles and returns deterministic mathematical
features. Everything upstream (data_engine) and downstream
(strategy_engine, not built yet) is a separate module by design.
"""

from app.data_engine.market_data import Candle
from app.technical_engine.indicators import calculate_sma
from app.technical_engine.models import TechnicalFeature


def calculate_features(candles: list[Candle]) -> list[TechnicalFeature]:
    """
    Requires `candles` to already be in chronological order (Phase 1's
    normalizer guarantees this for anything that went through the
    ingestion pipeline). This function does not re-sort — it verifies
    the precondition and fails loudly rather than silently computing
    indicators over misordered data, per the project's "fail clearly"
    rule.

    Uses CLOSE prices only, never open/high/low, per the technical
    engine's input contract.
    """
    if not candles:
        return []

    _require_chronological_order(candles)

    closes = [c.close for c in candles]
    sma_10_values = calculate_sma(closes, period=10)
    sma_50_values = calculate_sma(closes, period=50)

    return [
        TechnicalFeature(
            timestamp=candle.timestamp,
            close=candle.close,
            sma_10=sma_10_values[i],
            sma_50=sma_50_values[i],
        )
        for i, candle in enumerate(candles)
    ]


def _require_chronological_order(candles: list[Candle]) -> None:
    for i in range(1, len(candles)):
        if candles[i].timestamp <= candles[i - 1].timestamp:
            raise ValueError(
                "calculate_features requires strictly chronological, "
                f"duplicate-free candles. Out-of-order/duplicate pair found at "
                f"index {i}: {candles[i-1].timestamp.isoformat()} -> "
                f"{candles[i].timestamp.isoformat()}. Run candles through "
                "app.data_engine.normalizer.normalize_candles first."
            )
