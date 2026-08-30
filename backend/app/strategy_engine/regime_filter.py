"""
Regime filter — takes Phase 9's breakout signals EXACTLY as produced
(unmodified) and suppresses any BUY/SELL whose SIGNAL-CANDLE regime
(Phase 5's existing classification, reused unmodified — no new regime
logic here) is not in the allowed set. WAIT signals are always left
as WAIT. A suppressed BUY/SELL becomes WAIT, never silently dropped
from the list (same length in, same length out, same timestamps).

SIGNAL-TIME RULE (the critical guarantee): signal i is evaluated using
feature i's regime — the SAME candle the signal itself was generated
from. Never feature[i+1] or later. This is enforced simply by
construction (index-aligned, one pass, no lookahead into the feature
list at all) rather than by a runtime check — see
test_regime_filter.py for the explicit proof.
"""

from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot


def filter_signals_by_regime(
    signals: list[Signal], features: list[FeatureSnapshot], allowed_regimes: set[str]
) -> list[Signal]:
    if len(signals) != len(features):
        raise ValueError("signals and features must be the same length and aligned by index.")

    filtered: list[Signal] = []
    for signal, feature in zip(signals, features):
        if signal.direction in ("BUY", "SELL") and feature.regime not in allowed_regimes:
            filtered.append(
                Signal(
                    timestamp=signal.timestamp, symbol=signal.symbol, direction="WAIT",
                    sma_10=signal.sma_10, sma_50=signal.sma_50,
                    reason=(
                        f"Suppressed by regime filter: signal-time regime "
                        f"'{feature.regime}' not in {sorted(allowed_regimes)}. "
                        f"Original reason: {signal.reason}"
                    ),
                )
            )
        else:
            filtered.append(signal)

    return filtered
