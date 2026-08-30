"""
The backtesting engine.

Two entrypoints:

  simulate_trades(candles, signals, config) — the core, pure engine.
      Takes candles and an ALREADY-COMPUTED signal list (same length,
      same order) and simulates trading them. Contains zero SMA or
      crossover logic — this is what makes it possible to unit-test
      execution timing, spread, slippage, and P&L with exact,
      hand-verifiable numbers, by constructing Signal lists directly
      (the same technique test_crossover_strategy.py used for
      TechnicalFeature lists in Phase 3).

  run_backtest(candles, config) — the real entrypoint. Calls
      strategy_engine.run_crossover_strategy() to get signals, then
      delegates straight to simulate_trades(). This is the only
      function that touches technical_engine/strategy_engine, so
      those modules' logic is never duplicated here.

EXECUTION TIMING (Phase 4 spec section 6 — read this carefully):

A signal detected on candle T is NOT executed at candle T's price.
It is queued and executed at candle T+1's OPEN price — the first
price actually available after the signal-generating candle finished
forming. A signal on the very last candle in the dataset has no T+1
to execute at, so it is never executed (a documented, deliberate gap,
not a bug — you cannot trade on data that doesn't exist yet).

This queue-then-execute-next-candle structure is also what prevents
lookahead bias at the engine level (on top of the lookahead protection
already proven in technical_engine/strategy_engine): candle i's
execution logic only ever reads candle i's own open/close price and
state carried over from before candle i — never anything from i+1
onward.
"""

from app.backtesting.config import BacktestConfig
from app.backtesting.metrics import compute_metrics
from app.backtesting.models import BacktestResult
from app.backtesting.portfolio import Portfolio
from app.data_engine.market_data import Candle
from app.strategy_engine.models import Signal
from app.strategy_engine.service import run_crossover_strategy


def run_backtest(candles: list[Candle], config: BacktestConfig) -> BacktestResult:
    signals = run_crossover_strategy(candles, symbol=config.symbol)
    return simulate_trades(candles, signals, config)


def simulate_trades(
    candles: list[Candle], signals: list[Signal], config: BacktestConfig
) -> BacktestResult:
    if len(candles) != len(signals):
        raise ValueError(
            f"candles ({len(candles)}) and signals ({len(signals)}) must be the same length "
            "and in the same order — one signal per candle."
        )

    portfolio = Portfolio(config)

    if not candles:
        summary = compute_metrics([], [], config.initial_balance)
        return BacktestResult(configuration=config, summary=summary, trades=[], equity_curve=[])

    pending_signal: Signal | None = None

    for i, candle in enumerate(candles):
        # Execute any signal that was queued on the PREVIOUS candle —
        # this is the "next_open" execution model: today's open is the
        # first tradeable price after yesterday's signal.
        if pending_signal is not None:
            _execute_signal(portfolio, pending_signal, candle)
            pending_signal = None

        # Queue this candle's own signal (if any) for execution at the
        # NEXT candle — never at this candle's own price.
        signal = signals[i]
        if signal.direction in ("BUY", "SELL"):
            pending_signal = signal

        portfolio.mark_to_market(mid_price=candle.close, timestamp=candle.timestamp)

    # A signal queued on the very last candle has no next candle to
    # execute at — deliberately left unexecuted, not an error.

    if portfolio.position is not None:
        last_candle = candles[-1]
        portfolio.close_position(
            mid_price=last_candle.close, timestamp=last_candle.timestamp, reason="END_OF_DATA"
        )
        # The candle-loop already appended an equity point for this final
        # candle (marked BEFORE the close). Remove it and append the
        # correct post-close point instead, so the equity curve still has
        # exactly one point per candle, not two for the last one.
        portfolio.equity_curve.pop()
        portfolio.mark_to_market(mid_price=last_candle.close, timestamp=last_candle.timestamp)

    summary = compute_metrics(portfolio.trades, portfolio.equity_curve, config.initial_balance)
    return BacktestResult(
        configuration=config, summary=summary,
        trades=portfolio.trades, equity_curve=portfolio.equity_curve,
    )


def _execute_signal(portfolio: Portfolio, signal: Signal, execution_candle: Candle) -> None:
    new_direction = "LONG" if signal.direction == "BUY" else "SHORT"

    if portfolio.position is None:
        portfolio.open_position(
            direction=new_direction, mid_price=execution_candle.open,
            timestamp=execution_candle.timestamp, signal_timestamp=signal.timestamp,
            reason=signal.reason,
        )
    elif portfolio.position.direction != new_direction:
        portfolio.close_position(
            mid_price=execution_candle.open, timestamp=execution_candle.timestamp,
            reason=f"Reversed by opposite signal: {signal.reason}",
        )
        portfolio.open_position(
            direction=new_direction, mid_price=execution_candle.open,
            timestamp=execution_candle.timestamp, signal_timestamp=signal.timestamp,
            reason=signal.reason,
        )
    # else: signal agrees with the position we're already holding —
    # the crossover strategy should never emit this (it only signals
    # on the crossing candle), but if it ever did, this is a no-op
    # rather than illegally stacking a second position.
