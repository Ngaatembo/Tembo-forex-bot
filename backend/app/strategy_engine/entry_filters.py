"""
Entry filters for Phase 6 experiments.

Each filter takes the baseline SMA10/50 crossover signals (unmodified
— Phase 3's control) and returns a NEW signal list where some BUY/SELL
signals have been downgraded to WAIT. This never mutates the baseline
signal list, and never invents a new entry the baseline didn't already
find — filters can only SUPPRESS a baseline entry, never add one.

Both hypotheses below were pre-registered BEFORE looking at validation
or out-of-sample results — they came directly from Phase 5's
descriptive findings on the TRAIN_DEV period pattern (see
docs/phase-5-notes.md), and are frozen here rather than tuned against
whatever period they're evaluated on next. See docs/phase-6-notes.md
for the out-of-sample discipline this phase follows.

HYPOTHESIS E1 (avoid_low_volatility): Phase 5 found LOW_VOLATILITY-regime
baseline trades had the worst win rate (20%) and worst profit factor
(0.717) of the three regimes any trade occurred in. Economic rationale:
a crossover in a nearly flat market may be more noise-driven than
signal-driven. Filter: suppress any signal whose FeatureSnapshot at
signal time has regime == LOW_VOLATILITY.

HYPOTHESIS E2 (avoid_extreme_rsi): Phase 5 found RSI>=70-zone trades had
the worst profit factor (0.601) of the four RSI zones. Economic
rationale: a crossover firing while RSI is already extended in the
signal's direction may be entering late in a move. Filter: suppress
BUY signals where RSI>=70 at signal time, and SELL signals where
RSI<=30 (the symmetric case — a bearish crossover already deep in
oversold territory).
"""

from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot

LOW_VOLATILITY_LABEL = "LOW_VOLATILITY"
RSI_OVERBOUGHT_THRESHOLD = 70.0
RSI_OVERSOLD_THRESHOLD = 30.0


def _suppress(signal: Signal, reason_suffix: str) -> Signal:
    return Signal(
        timestamp=signal.timestamp, symbol=signal.symbol, direction="WAIT",
        sma_10=signal.sma_10, sma_50=signal.sma_50,
        reason=f"{signal.reason} [suppressed by entry filter: {reason_suffix}]",
    )


def filter_avoid_low_volatility(signals: list[Signal], features: list[FeatureSnapshot]) -> list[Signal]:
    if len(signals) != len(features):
        raise ValueError("signals and features must be the same length and aligned by candle.")

    result = []
    for signal, feature in zip(signals, features):
        if signal.direction in ("BUY", "SELL") and feature.regime == LOW_VOLATILITY_LABEL:
            result.append(_suppress(signal, "low_volatility_regime_at_signal"))
        else:
            result.append(signal)
    return result


def filter_avoid_extreme_rsi(signals: list[Signal], features: list[FeatureSnapshot]) -> list[Signal]:
    if len(signals) != len(features):
        raise ValueError("signals and features must be the same length and aligned by candle.")

    result = []
    for signal, feature in zip(signals, features):
        rsi = feature.rsi_14
        if signal.direction == "BUY" and rsi is not None and rsi >= RSI_OVERBOUGHT_THRESHOLD:
            result.append(_suppress(signal, f"rsi>={RSI_OVERBOUGHT_THRESHOLD}_at_buy_signal"))
        elif signal.direction == "SELL" and rsi is not None and rsi <= RSI_OVERSOLD_THRESHOLD:
            result.append(_suppress(signal, f"rsi<={RSI_OVERSOLD_THRESHOLD}_at_sell_signal"))
        else:
            result.append(signal)
    return result
