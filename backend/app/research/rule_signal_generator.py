"""
Turns a Hypothesis's entry_long/entry_short RuleSets into a Signal
list — the same shape Phase 3's crossover strategy produces, so it
can be fed directly into the existing (unmodified) backtesting engine.

FIRING SEMANTICS: a signal fires only on the state TRANSITION into a
condition being true (False/None -> True), mirroring the crossover
strategy's "only fire on the crossing candle" behavior — never
repeated on every subsequent candle the condition happens to remain
true. This is a deliberate design choice for consistency with the
rest of the project, not an accident of implementation.
"""

from app.data_engine.market_data import Candle
from app.research.hypothesis import Hypothesis
from app.research.rule_evaluation import evaluate_ruleset
from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot


def generate_signals_from_hypothesis(
    hypothesis: Hypothesis, candles: list[Candle], features: list[FeatureSnapshot]
) -> list[Signal]:
    if len(candles) != len(features):
        raise ValueError("candles and features must be the same length and aligned by index.")

    signals: list[Signal] = []
    prev_long: bool | None = None
    prev_short: bool | None = None

    for candle, feature in zip(candles, features):
        long_now = evaluate_ruleset(hypothesis.entry_long, feature)
        short_now = evaluate_ruleset(hypothesis.entry_short, feature)

        direction, reason = "WAIT", "No rule transition on this candle."

        if long_now is None or short_now is None:
            reason = "Insufficient data — inside feature warm-up period."
        elif long_now and not prev_long:
            direction, reason = "BUY", f"Entry-long rule became true ({hypothesis.id})."
        elif short_now and not prev_short:
            direction, reason = "SELL", f"Entry-short rule became true ({hypothesis.id})."

        signals.append(
            Signal(
                timestamp=feature.timestamp, symbol=hypothesis.market, direction=direction,
                sma_10=feature.sma_10, sma_50=feature.sma_50, reason=reason,
            )
        )
        prev_long, prev_short = long_now, short_now

    return signals
