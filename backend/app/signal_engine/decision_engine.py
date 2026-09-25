"""
Deterministic multi-factor trade-decision engine.

This module converts already-validated technical features and candlestick
observations into an auditable BUY/SELL/NO_TRADE research decision.
It never fetches data, calls an LLM, places orders, or changes account state.

All weights/thresholds are explicit Tembo starting hypotheses, not validated
performance claims. A missing required input fails closed to NO_TRADE.
"""

from dataclasses import asdict, dataclass
from typing import Any

from app.live_engine.candlesticks import PatternObservation
from app.technical_engine.models import FeatureSnapshot


@dataclass(frozen=True)
class FactorEvidence:
    name: str
    score: float
    direction: str
    reason: str


@dataclass(frozen=True)
class TradeDecision:
    decision: str
    direction: str
    confidence: float
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    factors: tuple[FactorEvidence, ...]
    rejection_reasons: tuple[str, ...]
    methodology: str = "TEMBO_MULTI_FACTOR_V1"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["factors"] = [asdict(item) for item in self.factors]
        d["rejection_reasons"] = list(self.rejection_reasons)
        return d


# Explicit starting weights; these are research parameters, not optimized values.
WEIGHTS = {
    "trend": 25.0,
    "momentum": 20.0,
    "structure": 20.0,
    "volatility": 15.0,
    "candlestick": 20.0,
}
MIN_DECISION_SCORE = 65.0
MIN_RISK_REWARD = 2.0
ATR_STOP_MULTIPLIER = 1.5


def _factor(name: str, score: float, direction: str, reason: str) -> FactorEvidence:
    return FactorEvidence(name, max(0.0, min(score, WEIGHTS[name])), direction, reason)


def _directional_factors(
    feature: FeatureSnapshot,
    patterns: list[PatternObservation],
) -> tuple[list[FactorEvidence], list[str]]:
    factors: list[FactorEvidence] = []
    reasons: list[str] = []

    # Trend: require a directional regime and price/SMA alignment.
    if feature.regime == "TRENDING_UP":
        factors.append(_factor("trend", 25, "BUY", "Price and SMA structure are aligned upward."))
    elif feature.regime == "TRENDING_DOWN":
        factors.append(_factor("trend", 25, "SELL", "Price and SMA structure are aligned downward."))
    elif feature.regime == "UNKNOWN":
        factors.append(_factor("trend", 0, "NONE", "Trend regime is not available during feature warm-up."))
        reasons.append("Trend regime is unknown.")
    else:
        factors.append(_factor("trend", 0, "NONE", f"Regime {feature.regime} does not establish a directional trend."))

    # Momentum: RSI is deliberately treated as directional confirmation,
    # not as an isolated overbought/oversold trigger.
    if feature.rsi_14 is None:
        factors.append(_factor("momentum", 0, "NONE", "RSI is unavailable."))
        reasons.append("Momentum data is unavailable.")
    elif feature.regime == "TRENDING_UP" and 50.0 <= feature.rsi_14 < 70.0:
        factors.append(_factor("momentum", 20, "BUY", f"RSI {feature.rsi_14:.1f} confirms positive momentum without being overextended."))
    elif feature.regime == "TRENDING_DOWN" and 30.0 < feature.rsi_14 <= 50.0:
        factors.append(_factor("momentum", 20, "SELL", f"RSI {feature.rsi_14:.1f} confirms negative momentum without being deeply oversold."))
    else:
        factors.append(_factor("momentum", 0, "NONE", f"RSI {feature.rsi_14:.1f} does not confirm the current directional regime."))

    # Structure: use distance from recent extremes. In a trend, being away
    # from the wrong extreme supports continuation; chasing a fresh extreme
    # is rejected rather than assumed safe.
    if feature.recent_high is None or feature.recent_low is None or feature.rolling_range in (None, 0):
        factors.append(_factor("structure", 0, "NONE", "Recent structure is unavailable."))
        reasons.append("Market structure is unavailable.")
    else:
        if feature.regime == "TRENDING_UP":
            location = (feature.close - feature.recent_low) / feature.rolling_range
            if 0.20 <= location <= 0.80:
                factors.append(_factor("structure", 20, "BUY", "Price is inside the recent range rather than at its upper extreme."))
            else:
                factors.append(_factor("structure", 0, "NONE", "Price location is too close to a recent range extreme."))
        elif feature.regime == "TRENDING_DOWN":
            location = (feature.close - feature.recent_low) / feature.rolling_range
            if 0.20 <= location <= 0.80:
                factors.append(_factor("structure", 20, "SELL", "Price is inside the recent range rather than at its lower extreme."))
            else:
                factors.append(_factor("structure", 0, "NONE", "Price location is too close to a recent range extreme."))
        else:
            factors.append(_factor("structure", 0, "NONE", "No directional structure established."))

    # Volatility: high volatility is a hard rejection; normal volatility
    # contributes evidence. Low volatility is not automatically bullish/bearish.
    if feature.atr_14 is None or feature.atr_percent is None:
        factors.append(_factor("volatility", 0, "NONE", "ATR is unavailable."))
        reasons.append("Volatility data is unavailable.")
    elif feature.regime == "HIGH_VOLATILITY":
        factors.append(_factor("volatility", 0, "NONE", "High volatility regime is excluded by the starting risk policy."))
        reasons.append("High volatility regime.")
    elif feature.atr_14 > 0:
        factors.append(_factor("volatility", 15, "BOTH", "ATR is available and volatility is not classified as high."))

    # Candlestick evidence: only confirmed observations count.
    directional = [p for p in patterns if p.confirmed and p.direction in {"BULLISH", "BEARISH"}]
    bull = any(p.direction == "BULLISH" for p in directional)
    bear = any(p.direction == "BEARISH" for p in directional)
    if bull and not bear:
        factors.append(_factor("candlestick", 20, "BUY", "Confirmed bullish candlestick evidence is present."))
    elif bear and not bull:
        factors.append(_factor("candlestick", 20, "SELL", "Confirmed bearish candlestick evidence is present."))
    elif bull and bear:
        factors.append(_factor("candlestick", 0, "NONE", "Confirmed bullish and bearish candle evidence conflict."))
        reasons.append("Candlestick evidence conflicts.")
    else:
        factors.append(_factor("candlestick", 0, "NONE", "No confirmed directional candlestick evidence."))

    return factors, reasons


def evaluate_trade_decision(
    feature: FeatureSnapshot,
    patterns: list[PatternObservation],
) -> TradeDecision:
    if feature.close <= 0:
        return TradeDecision("NO_TRADE", "NONE", 0, None, None, None, None, (), ("Invalid/non-positive price.",))

    if feature.atr_14 is None or feature.atr_14 <= 0:
        return TradeDecision("NO_TRADE", "NONE", 0, feature.close, None, None, None, (), ("ATR is unavailable or invalid.",))

    factors, rejection_reasons = _directional_factors(feature, patterns)

    buy_score = sum(f.score for f in factors if f.direction == "BUY")
    sell_score = sum(f.score for f in factors if f.direction == "SELL")
    best_score = max(buy_score, sell_score)
    direction = "BUY" if buy_score > sell_score else "SELL" if sell_score > buy_score else "NONE"

    if feature.regime == "HIGH_VOLATILITY":
        rejection_reasons.append("High volatility blocks the decision.")
    if direction == "NONE":
        rejection_reasons.append("No directional multi-factor edge.")
    elif best_score < MIN_DECISION_SCORE:
        rejection_reasons.append(f"Evidence score {best_score:.1f} is below the {MIN_DECISION_SCORE:.1f} threshold.")

    entry = feature.close
    stop_distance = feature.atr_14 * ATR_STOP_MULTIPLIER
    if direction == "BUY":
        stop = entry - stop_distance
        target = entry + stop_distance * MIN_RISK_REWARD
    elif direction == "SELL":
        stop = entry + stop_distance
        target = entry - stop_distance * MIN_RISK_REWARD
    else:
        return TradeDecision(
            "NO_TRADE", "NONE", round(best_score, 2), entry, None, None, None,
            tuple(factors), tuple(dict.fromkeys(rejection_reasons)),
        )

    rr = abs(target - entry) / abs(entry - stop)
    if rr < MIN_RISK_REWARD:
        rejection_reasons.append("Risk/reward is below the minimum threshold.")

    if rejection_reasons:
        return TradeDecision(
            "NO_TRADE", direction, round(best_score, 2), entry, stop, target, round(rr, 2),
            tuple(factors), tuple(dict.fromkeys(rejection_reasons)),
        )

    return TradeDecision(
        direction, direction, round(best_score, 2), entry, stop, target, round(rr, 2),
        tuple(factors), (),
    )
