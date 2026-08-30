"""
Exit rule configuration for Phase 6 experiments.

Each field represents an INDEPENDENT exit mechanism. Per the Phase 6
spec's explicit instruction not to combine hypotheses immediately,
every experiment in this phase enables exactly ONE non-baseline
mechanism at a time (plus the always-on baseline opposite-crossover
exit, which never gets disabled — every experimental exit is
"baseline OR this new condition, whichever triggers first").

STOP/TARGET PRICE DERIVATION:
  - Fixed stop/take-profit: a fixed PERCENTAGE of entry price
    (e.g. stop_loss_pct=0.01 = a 1% adverse move from entry)
  - ATR-based stop/take-profit: entry price +/- (atr_multiple * ATR14
    AT THE MOMENT OF ENTRY) — the ATR value is frozen at entry, not
    recalculated candle-by-candle, which is the standard convention
    for an "ATR stop" (a moving/trailing ATR stop is a DIFFERENT,
    more complex hypothesis, not implemented in Phase 6)

MAX HOLDING PERIOD: measured in CANDLES (1 candle = 1 hour on this
strategy's timeframe), not calendar time.
"""

from dataclasses import dataclass


@dataclass
class ExitConfig:
    label: str  # e.g. "baseline", "fixed_stop_1pct", "atr_stop_2x" — used in experiment records

    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    atr_stop_multiple: float | None = None
    atr_take_profit_multiple: float | None = None
    max_holding_candles: int | None = None

    def __post_init__(self):
        active = [
            self.stop_loss_pct is not None, self.take_profit_pct is not None,
            self.atr_stop_multiple is not None, self.atr_take_profit_multiple is not None,
            self.max_holding_candles is not None,
        ]
        if self.stop_loss_pct is not None and self.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be positive (a fraction, e.g. 0.01 for 1%).")
        if self.take_profit_pct is not None and self.take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive.")
        if self.max_holding_candles is not None and self.max_holding_candles <= 0:
            raise ValueError("max_holding_candles must be a positive integer.")
        if self.stop_loss_pct is not None and self.atr_stop_multiple is not None:
            raise ValueError(
                "Cannot set both stop_loss_pct and atr_stop_multiple — pick one stop "
                "mechanism per experiment (Phase 6 tests one variable at a time)."
            )
        if self.take_profit_pct is not None and self.atr_take_profit_multiple is not None:
            raise ValueError(
                "Cannot set both take_profit_pct and atr_take_profit_multiple — pick one "
                "target mechanism per experiment."
            )


BASELINE_EXIT = ExitConfig(label="baseline_opposite_crossover_only")


def compute_stop_target_prices(
    *, direction: str, entry_price: float, entry_atr_14: float | None, exit_config: ExitConfig,
) -> tuple[float | None, float | None]:
    """
    Returns (stop_price, target_price), either of which may be None.
    entry_atr_14 is required (and must not be None) if the config uses
    an ATR-based mechanism — raises clearly rather than silently
    producing no stop if ATR wasn't available (e.g. still in warm-up).
    """
    sign = 1 if direction == "LONG" else -1

    stop_price = None
    if exit_config.stop_loss_pct is not None:
        stop_price = entry_price - sign * exit_config.stop_loss_pct * entry_price
    elif exit_config.atr_stop_multiple is not None:
        if entry_atr_14 is None:
            raise ValueError("ATR-based stop requires a non-None ATR14 value at entry.")
        stop_price = entry_price - sign * exit_config.atr_stop_multiple * entry_atr_14

    target_price = None
    if exit_config.take_profit_pct is not None:
        target_price = entry_price + sign * exit_config.take_profit_pct * entry_price
    elif exit_config.atr_take_profit_multiple is not None:
        if entry_atr_14 is None:
            raise ValueError("ATR-based take-profit requires a non-None ATR14 value at entry.")
        target_price = entry_price + sign * exit_config.atr_take_profit_multiple * entry_atr_14

    return stop_price, target_price
