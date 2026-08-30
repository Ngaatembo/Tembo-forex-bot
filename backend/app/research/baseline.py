"""
The frozen baseline: SMA10/50 crossover, unmodified since Phase 3.

FROZEN_BASELINE_ID below and the documented full-period figures are a
historical reference point (from Phase 4.5's real validation) — they
must never be silently edited to match a new run. For actual
period-by-period comparisons in this phase's experiments,
compute_baseline_summary() below reruns the exact unmodified Phase 4
`run_backtest()` on whatever candle slice an experiment uses — this is
the SAME baseline logic, not a re-implementation, applied fresh to
whatever period is being compared against.
"""

from dataclasses import dataclass

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest
from app.backtesting.models import BacktestSummary
from app.data_engine.market_data import Candle

FROZEN_BASELINE_ID = "BASELINE_SMA_10_50_V1"

# Historical reference figures — Phase 4.5, full period (2012-11-16 to
# 2022-03-04, 57,600 candles), BASE_COST config. Documented, not
# recomputed here — see docs/phase-4-5-real-historical-validation.md
# for the original source of these numbers.
FROZEN_BASELINE_HISTORICAL_REFERENCE = {
    "trade_count": 1539,
    "zero_cost_profit_factor": 0.9405,
    "zero_cost_return": -0.2146,
    "base_cost_return": -0.4300,
    "max_drawdown_percent": 0.6132,
}


def compute_baseline_summary(candles: list[Candle], config: BacktestConfig) -> BacktestSummary:
    """Runs the actual, unmodified Phase 3 strategy + Phase 4 engine on
    the given candles — the real baseline for whatever period an
    experiment is being compared against, not a stored/stale number."""
    result = run_backtest(candles, config)
    return result.summary
