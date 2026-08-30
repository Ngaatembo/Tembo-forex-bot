"""
Deterministic market-regime classification.

These are ALGORITHMIC LABELS based on explicit, documented rules —
not objective truths about "what the market is really doing." The
thresholds below were chosen to be simple and defensible as a
starting point; they were NOT tuned or searched against any backtest
P&L. If they turn out to be poorly calibrated, that's a finding for
later research, not something to silently adjust to make results
look better.

REGIME DEFINITIONS (exact rules, in priority order):

1. UNKNOWN — any required input (SMA50 slope, ATR%, SMA distance) is
   still None (warm-up period not yet complete for that feature).

2. HIGH_VOLATILITY — atr_percent > 0.0015 (0.15% of price per candle).
   Checked BEFORE trend conditions: a highly volatile candle is
   classified by its volatility first, regardless of trend shape,
   since high volatility materially changes what a "trend" even means.

3. LOW_VOLATILITY — atr_percent < 0.0005 (0.05% of price per candle).

4. TRENDING_UP — none of the above, AND: close > sma_50, AND
   sma_50_slope > 0, AND sma_distance_pct > 0.0010 (SMA10 at least
   0.10% above SMA50 — "sufficient separation," not just barely
   crossed).

5. TRENDING_DOWN — the exact mirror: close < sma_50, sma_50_slope < 0,
   sma_distance_pct < -0.0010.

6. RANGING — none of the above conditions are met. This is the
   default/fallback, not a positively-defined state.

These thresholds are EUR/USD-1H-shaped guesses, not calibrated
against this or any other instrument's actual volatility distribution.
A different instrument or timeframe would likely need different
threshold values — using these as-is elsewhere would be a mistake.
"""

from dataclasses import dataclass
from enum import Enum


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


# Documented, not-optimized starting thresholds — see module docstring.
HIGH_VOLATILITY_ATR_PCT_THRESHOLD = 0.0015
LOW_VOLATILITY_ATR_PCT_THRESHOLD = 0.0005
TREND_SEPARATION_PCT_THRESHOLD = 0.0010


@dataclass
class RegimeInputs:
    close: float | None
    sma_50: float | None
    sma_50_slope: float | None
    sma_distance_pct: float | None
    atr_percent: float | None


def classify_regime(inputs: RegimeInputs) -> MarketRegime:
    if (
        inputs.close is None or inputs.sma_50 is None or inputs.sma_50_slope is None
        or inputs.sma_distance_pct is None or inputs.atr_percent is None
    ):
        return MarketRegime.UNKNOWN

    if inputs.atr_percent > HIGH_VOLATILITY_ATR_PCT_THRESHOLD:
        return MarketRegime.HIGH_VOLATILITY
    if inputs.atr_percent < LOW_VOLATILITY_ATR_PCT_THRESHOLD:
        return MarketRegime.LOW_VOLATILITY

    if (
        inputs.close > inputs.sma_50 and inputs.sma_50_slope > 0
        and inputs.sma_distance_pct > TREND_SEPARATION_PCT_THRESHOLD
    ):
        return MarketRegime.TRENDING_UP

    if (
        inputs.close < inputs.sma_50 and inputs.sma_50_slope < 0
        and inputs.sma_distance_pct < -TREND_SEPARATION_PCT_THRESHOLD
    ):
        return MarketRegime.TRENDING_DOWN

    return MarketRegime.RANGING
