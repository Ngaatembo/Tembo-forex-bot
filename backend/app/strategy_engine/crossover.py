"""
Moving average crossover strategy.

Architectural boundary (same principle as technical_engine): this
module takes TechnicalFeature values in and returns Signal values out.
It never fetches data, never touches the database or a broker, never
calls an LLM, and never places an order. It does not backtest itself
either — that's Phase 4, which will replay these signals against
historical data and simulated costs.

STRATEGY DEFINITION (matches the plan agreed at the start of this
project — see docs/phase-3-notes.md for the full writeup):

  BUY  when SMA10 crosses from at-or-below SMA50 to strictly above it
  SELL when SMA10 crosses from at-or-above SMA50 to strictly below it
  WAIT on every other candle — including the entire warm-up period
       (either SMA is None), and including every candle where SMA10
       stays on the same side of SMA50 as it was already on

A signal fires ONLY on the candle where the cross actually happens —
never repeated on every subsequent candle where the fast MA happens to
remain above/below the slow one. That distinction is what keeps this a
crossover strategy instead of a "trend direction" indicator.
"""

from app.strategy_engine.models import Signal
from app.technical_engine.models import TechnicalFeature


def detect_crossover_signals(features: list[TechnicalFeature], symbol: str) -> list[Signal]:
    signals: list[Signal] = []
    prev_diff: float | None = None

    for feature in features:
        sma_10, sma_50 = feature.sma_10, feature.sma_50

        if sma_10 is None or sma_50 is None:
            signals.append(
                Signal(
                    timestamp=feature.timestamp, symbol=symbol, direction="WAIT",
                    sma_10=sma_10, sma_50=sma_50,
                    reason="Insufficient data — inside SMA warm-up period.",
                )
            )
            prev_diff = None
            continue

        diff = sma_10 - sma_50

        if prev_diff is not None and prev_diff <= 0 and diff > 0:
            direction, reason = "BUY", "SMA10 crossed above SMA50."
        elif prev_diff is not None and prev_diff >= 0 and diff < 0:
            direction, reason = "SELL", "SMA10 crossed below SMA50."
        else:
            direction, reason = "WAIT", "No crossover on this candle."

        signals.append(
            Signal(
                timestamp=feature.timestamp, symbol=symbol, direction=direction,
                sma_10=sma_10, sma_50=sma_50, reason=reason,
            )
        )
        prev_diff = diff

    return signals
