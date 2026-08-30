"""
Phase 6 research backtesting engine.

This is a SEPARATE function from Phase 4's `simulate_trades()` /
`run_backtest()` — those are untouched and remain the frozen baseline.
This module adds configurable stop-loss / take-profit / max-holding-
period exits on top of the same entry logic and cost model, for
controlled entry/exit experiments.

EXECUTION ORDER PER CANDLE (read this before trusting any experiment
result — it determines exactly what "at entry" and "intra-candle"
mean here):

  1. If a position is open, check whether this candle's high/low
     touched its stop or target, OR whether max-holding-period has
     elapsed. If so, close it — at the EXACT stop/target price for
     stop/target hits (a simplifying assumption: no extra slippage
     past the trigger price — see docs/phase-6-notes.md), or at this
     candle's open for a max-holding close (same timing convention as
     a normal signal exit).
  2. If a signal was queued from the PREVIOUS candle (next_open model,
     unchanged from Phase 4): if a position is still open and the
     queued signal is a REVERSAL, close it via the normal cost-model
     exit, then open the new position. If no position is open (either
     never opened, or just closed in step 1), open fresh.
  3. Queue this candle's own signal (if BUY/SELL) for execution next candle.
  4. Mark equity to market using this candle's close.

New positions get a stop/target price computed from THIS candle's
values (entry price = this candle's open; ATR, if the exit rule uses
one, = this candle's ATR14 — i.e. ATR "at entry", frozen, not
recalculated candle-by-candle).
"""

from app.backtesting.config import BacktestConfig
from app.backtesting.exit_rules import ExitConfig, compute_stop_target_prices
from app.backtesting.metrics import compute_metrics
from app.backtesting.models import BacktestResult
from app.backtesting.portfolio import Portfolio
from app.data_engine.market_data import Candle
from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot


def simulate_trades_with_exit_rules(
    candles: list[Candle], signals: list[Signal], features: list[FeatureSnapshot],
    config: BacktestConfig, exit_config: ExitConfig,
) -> BacktestResult:
    if not (len(candles) == len(signals) == len(features)):
        raise ValueError("candles, signals, and features must all be the same length and aligned.")

    portfolio = Portfolio(config)

    if not candles:
        summary = compute_metrics([], [], config.initial_balance)
        return BacktestResult(configuration=config, summary=summary, trades=[], equity_curve=[])

    pending_signal: Signal | None = None

    for i, candle in enumerate(candles):
        # Step 1 — check stop/target/max-holding for an already-open position.
        if portfolio.position is not None:
            reason = portfolio.check_exit_conditions(
                candle_high=candle.high, candle_low=candle.low, candle_index=i
            )
            if reason == "STOP_LOSS":
                portfolio.close_position_at_price(
                    exact_price=portfolio.position.stop_price, timestamp=candle.timestamp, reason=reason
                )
            elif reason == "TAKE_PROFIT":
                portfolio.close_position_at_price(
                    exact_price=portfolio.position.target_price, timestamp=candle.timestamp, reason=reason
                )
            elif reason == "MAX_HOLDING_PERIOD":
                portfolio.close_position(mid_price=candle.open, timestamp=candle.timestamp, reason=reason)

        # Step 2 — execute any signal queued from the previous candle.
        if pending_signal is not None:
            _execute_signal(portfolio, pending_signal, candle, features[i], exit_config, entry_index=i)
            pending_signal = None

        # Step 3 — queue this candle's own signal for next-candle execution.
        signal = signals[i]
        if signal.direction in ("BUY", "SELL"):
            pending_signal = signal

        # Step 4 — mark to market.
        portfolio.mark_to_market(mid_price=candle.close, timestamp=candle.timestamp)

    if portfolio.position is not None:
        last_candle = candles[-1]
        portfolio.close_position(
            mid_price=last_candle.close, timestamp=last_candle.timestamp, reason="END_OF_DATA"
        )
        portfolio.equity_curve.pop()
        portfolio.mark_to_market(mid_price=last_candle.close, timestamp=last_candle.timestamp)

    summary = compute_metrics(portfolio.trades, portfolio.equity_curve, config.initial_balance)
    return BacktestResult(
        configuration=config, summary=summary,
        trades=portfolio.trades, equity_curve=portfolio.equity_curve,
    )


def _execute_signal(
    portfolio: Portfolio, signal: Signal, execution_candle: Candle,
    execution_feature: FeatureSnapshot, exit_config: ExitConfig, entry_index: int,
) -> None:
    new_direction = "LONG" if signal.direction == "BUY" else "SHORT"

    if portfolio.position is not None and portfolio.position.direction == new_direction:
        return  # already holding this direction — no-op, same as the baseline engine

    if portfolio.position is not None:
        portfolio.close_position(
            mid_price=execution_candle.open, timestamp=execution_candle.timestamp,
            reason=f"Reversed by opposite signal: {signal.reason}",
        )

    entry_price = execution_candle.open
    try:
        stop_price, target_price = compute_stop_target_prices(
            direction=new_direction, entry_price=entry_price,
            entry_atr_14=execution_feature.atr_14, exit_config=exit_config,
        )
    except ValueError:
        # ATR-based exit requested but ATR wasn't available at this
        # candle (rare — ATR14 warms up well before SMA50 does, but
        # guarded anyway). Skip opening this particular trade rather
        # than crash or silently open with no stop.
        return

    portfolio.open_position(
        direction=new_direction, mid_price=entry_price, timestamp=execution_candle.timestamp,
        signal_timestamp=signal.timestamp, reason=signal.reason,
        stop_price=stop_price, target_price=target_price,
        entry_candle_index=entry_index, max_holding_candles=exit_config.max_holding_candles,
    )
