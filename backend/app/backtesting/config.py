"""
Backtest configuration.

Every tunable value the engine uses lives here — nothing is
hard-coded inside engine logic. Two fields (`execution_model`,
`end_of_data_policy`) currently accept only one value each; they exist
as explicit config now so a future phase can add alternatives
(e.g. same-candle-close execution, or leaving positions open past the
dataset) without changing every call site — Phase 4 deliberately
supports exactly one policy for each and raises clearly if asked for
anything else.
"""

from dataclasses import dataclass


@dataclass
class BacktestConfig:
    symbol: str = "EUR/USD"
    timeframe: str = "1h"

    initial_balance: float = 1000.0

    # Fixed notional size per trade, in units of the base currency —
    # e.g. 10_000 is loosely analogous to a "mini lot". This is a
    # deliberately simple placeholder for Phase 4A: no margin, no
    # leverage, no lot-size constraints are modeled. Real risk-based
    # position sizing is a later phase (risk_engine, Phase 8+).
    position_size: float = 10_000.0

    # EXAMPLE/TEST VALUE — NOT a claim about real EUR/USD market spread.
    # Expressed in price units (0.00010 = 1 pip on EUR/USD). Applied as
    # a half-spread cost on each side of a trade (pay the ask to buy,
    # receive the bid to sell) — see portfolio.py.
    spread: float = 0.00010

    # Fixed price-unit slippage applied against the trader on every
    # execution (buys get worse, sells get worse) — 0.0 by default so
    # unit tests can compute exact expected P&L. Must be set explicitly
    # for realistic experiments; never silently assumed to be zero in
    # results presented as "realistic".
    slippage: float = 0.0

    # Only "next_open" is implemented in Phase 4: a signal generated on
    # candle T executes at candle T+1's open price. A signal can never
    # execute at its own candle's close, because that price wasn't
    # known until the candle had already finished forming.
    execution_model: str = "next_open"

    # Only "close" is implemented in Phase 4: a position still open
    # when the dataset ends is closed at the final candle's close
    # price and the trade is tagged exit_reason="END_OF_DATA" — never
    # silently dropped.
    end_of_data_policy: str = "close"

    def __post_init__(self):
        if self.execution_model != "next_open":
            raise NotImplementedError(
                f"execution_model={self.execution_model!r} is not implemented in Phase 4. "
                "Only 'next_open' is supported."
            )
        if self.end_of_data_policy != "close":
            raise NotImplementedError(
                f"end_of_data_policy={self.end_of_data_policy!r} is not implemented in Phase 4. "
                "Only 'close' is supported."
            )
        if self.position_size <= 0:
            raise ValueError("position_size must be positive.")
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be positive.")
        if self.spread < 0 or self.slippage < 0:
            raise ValueError("spread and slippage must be >= 0.")
