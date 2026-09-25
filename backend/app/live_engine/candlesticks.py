"""Deterministic candlestick intelligence derived from the uploaded books.

The book-derived geometry is kept separate from Tembo's own operational
context rules. Pattern detection never emits a BUY/SELL order. It emits
evidence that the later decision engine may combine with trend, structure,
momentum, volatility, news and the Risk Engine.

Important: the books describe pattern meaning qualitatively. Where code
needs a numerical threshold (for example what counts as "very small"), the
threshold is explicitly documented as a Tembo operationalization, not as
a claim made by the source.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PatternObservation:
    name: str
    direction: str
    context: str
    confirmed: bool
    confirmation_required: bool
    strength: str
    evidence: tuple[str, ...]
    source_basis: str


def _body(c: Any) -> float:
    return abs(c.close - c.open)


def _range(c: Any) -> float:
    return max(c.high - c.low, 1e-12)


def _upper(c: Any) -> float:
    return c.high - max(c.open, c.close)


def _lower(c: Any) -> float:
    return min(c.open, c.close) - c.low


def _bull(c: Any) -> bool:
    return c.close > c.open


def _bear(c: Any) -> bool:
    return c.close < c.open


def trend_context(candles: list[Any], lookback: int = 10) -> str:
    """Operationalize the books' required prior-trend context.

    The sources require a definite prior trend but do not prescribe a
    numeric trend detector. Tembo uses the last lookback completed closes:
    at least half directional and at least 0.2% net movement defines UP/DOWN.
    Otherwise the context is SIDEWAYS/UNKNOWN.
    """
    if len(candles) < lookback + 1:
        return "UNKNOWN"
    closes = [c.close for c in candles[-lookback - 1 :]]
    net_move = (closes[-1] - closes[0]) / max(abs(sum(closes) / len(closes)), 1e-12)
    rising = sum(closes[i] > closes[i - 1] for i in range(1, len(closes)))
    falling = sum(closes[i] < closes[i - 1] for i in range(1, len(closes)))
    if net_move >= 0.002 and rising >= lookback * 0.5:
        return "UP"
    if net_move <= -0.002 and falling >= lookback * 0.5:
        return "DOWN"
    return "SIDEWAYS"


def _single_reversal_shape(candle: Any, context: str) -> tuple[str, str, tuple[str, ...]] | None:
    body = _body(candle)
    upper = _upper(candle)
    lower = _lower(candle)

    if lower >= 2 * body and upper <= body:
        if context == "DOWN":
            return (
                "HAMMER",
                "BULLISH",
                ("lower_shadow>=2x_body", "small_upper_shadow", "downtrend_context"),
            )
        if context == "UP":
            return (
                "HANGING_MAN",
                "BEARISH",
                ("lower_shadow>=2x_body", "small_upper_shadow", "uptrend_context"),
            )

    if upper >= 2 * body and lower <= body:
        if context == "UP":
            return (
                "SHOOTING_STAR",
                "BEARISH",
                ("upper_shadow>=2x_body", "small_lower_shadow", "uptrend_context"),
            )
        if context == "DOWN":
            return (
                "INVERTED_HAMMER",
                "BULLISH",
                ("upper_shadow>=2x_body", "small_lower_shadow", "downtrend_context"),
            )

    return None


def detect_candlestick_patterns(candles: list[Any]) -> list[PatternObservation]:
    """Detect source-described patterns from completed candles only.

    The detector deliberately does not look ahead. For patterns whose
    source requires next-candle confirmation, confirmed is False until that
    next candle exists and closes in the required direction.
    """
    if len(candles) < 2:
        return []

    current = candles[-1]
    context = trend_context(candles[:-1])
    body = _body(current)
    candle_range = _range(current)
    upper = _upper(current)
    lower = _lower(current)
    observations: list[PatternObservation] = []

    # The introduction defines a doji as an open/close that are the same
    # or very close. <=10% of the range is Tembo's explicit numeric proxy.
    if body / candle_range <= 0.10:
        observations.append(
            PatternObservation(
                "DOJI", "NEUTRAL", context, True, False, "CONTEXTUAL",
                ("open_close_near_equal",),
                "Japanese candlestick introduction: doji = little/no real body.",
            )
        )

    # Hammer / Hanging Man: same geometry, different trend context.
    if lower >= 2 * body and upper <= body:
        if context == "DOWN":
            observations.append(
                PatternObservation(
                    "HAMMER", "BULLISH", context,
                    False, True, "CONTEXTUAL",
                    ("lower_shadow>=2x_body", "small_upper_shadow", "downtrend_context"),
                    "21 Candlesticks + Japanese candlestick introduction.",
                )
            )
        elif context == "UP":
            observations.append(
                PatternObservation(
                    "HANGING_MAN", "BEARISH", context,
                    False, True, "CONTEXTUAL",
                    ("lower_shadow>=2x_body", "small_upper_shadow", "uptrend_context"),
                    "21 Candlesticks + Japanese candlestick introduction.",
                )
            )

    # Shooting Star / Inverted Hammer: same basic geometry, different context.
    if upper >= 2 * body and lower <= body:
        if context == "UP":
            observations.append(
                PatternObservation(
                    "SHOOTING_STAR", "BEARISH", context,
                    _confirmation(candles, "BEARISH"), True, "CONTEXTUAL",
                    ("upper_shadow>=2x_body", "small_lower_shadow", "uptrend_context"),
                    "21 Candlesticks + Japanese candlestick introduction.",
                )
            )
        elif context == "DOWN":
            observations.append(
                PatternObservation(
                    "INVERTED_HAMMER", "BULLISH", context,
                    _confirmation(candles, "BULLISH"), True, "CONTEXTUAL",
                    ("upper_shadow>=2x_body", "small_lower_shadow", "downtrend_context"),
                    "Japanese candlestick introduction.",
                )
            )

    # A reversal candle is not confirmed by itself. When the current
    # candle is the confirmation candle, report the immediately preceding
    # reversal pattern as confirmed. This preserves the source's "next day"
    # requirement without looking into the future.
    if len(candles) >= 3:
        prior = candles[-2]
        prior_context = trend_context(candles[:-2])
        prior_shape = _single_reversal_shape(prior, prior_context)
        if prior_shape is not None:
            name, direction, evidence = prior_shape
            confirms = current.close > prior.close if direction == "BULLISH" else current.close < prior.close
            if confirms:
                observations.append(
                    PatternObservation(
                        name, direction, prior_context,
                        True, True, "CONFIRMED",
                        evidence + ("next_candle_confirmation",),
                        "21 Candlesticks + Japanese candlestick introduction.",
                    )
                )

    if len(candles) >= 2:
        previous = candles[-2]
        midpoint = (previous.open + previous.close) / 2

        if _bear(previous) and _bull(current):
            if current.open <= previous.close and current.close >= previous.open and context == "DOWN":
                observations.append(
                    PatternObservation(
                        "BULLISH_ENGULFING", "BULLISH", context,
                        True, False, "STRONG",
                        ("downtrend_context", "current_body_engulfs_prior_body"),
                        "Japanese candlestick introduction.",
                    )
                )

        if _bull(previous) and _bear(current):
            if current.open >= previous.close and current.close <= previous.open and context == "UP":
                observations.append(
                    PatternObservation(
                        "BEARISH_ENGULFING", "BEARISH", context,
                        True, False, "STRONG",
                        ("uptrend_context", "current_body_engulfs_prior_body"),
                        "Japanese candlestick introduction.",
                    )
                )

        # Strict source form: gap above prior high / below prior low.
        # Forex often has fewer gaps, so this stays strict rather than
        # silently becoming a different pattern.
        if _bull(previous) and _bear(current):
            if current.open > previous.high and current.close < midpoint:
                observations.append(
                    PatternObservation(
                        "DARK_CLOUD_COVER", "BEARISH", context,
                        True, False, "CONTEXTUAL",
                        ("opens_above_prior_high", "closes_below_prior_body_midpoint"),
                        "Japanese candlestick introduction.",
                    )
                )

        if _bear(previous) and _bull(current):
            if current.open < previous.low and current.close > midpoint:
                observations.append(
                    PatternObservation(
                        "PIERCING_PATTERN", "BULLISH", context,
                        True, False, "CONTEXTUAL",
                        ("opens_below_prior_low", "closes_above_prior_body_midpoint"),
                        "Japanese candlestick introduction.",
                    )
                )

    if len(candles) >= 3:
        first, middle, third = candles[-3:]
        if (
            _bear(first)
            and _body(middle) <= _body(first) * 0.5
            and _bull(third)
            and third.close > (first.open + first.close) / 2
        ):
            observations.append(
                PatternObservation(
                    "MORNING_STAR", "BULLISH", context,
                    True, False, "STRONG",
                    ("long_bearish_first", "small_middle_body", "third_close_above_midpoint"),
                    "Japanese candlestick introduction.",
                )
            )
        if (
            _bull(first)
            and _body(middle) <= _body(first) * 0.5
            and _bear(third)
            and third.close < (first.open + first.close) / 2
        ):
            observations.append(
                PatternObservation(
                    "EVENING_STAR", "BEARISH", context,
                    True, False, "STRONG",
                    ("long_bullish_first", "small_middle_body", "third_close_below_midpoint"),
                    "Japanese candlestick introduction.",
                )
            )

    return observations


def observations_to_dict(observations: list[PatternObservation]) -> list[dict]:
    return [
        {
            "name": item.name,
            "direction": item.direction,
            "context": item.context,
            "confirmed": item.confirmed,
            "confirmation_required": item.confirmation_required,
            "strength": item.strength,
            "evidence": list(item.evidence),
            "source_basis": item.source_basis,
        }
        for item in observations
    ]
