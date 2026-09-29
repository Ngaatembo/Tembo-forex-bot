"""
Shadow scoreboard: paper-only forward tracking of researched setups.

Why: the one setup allowed on the demo account (USD/JPY H1 breakout) fires
about 6 times a month, so real evidence takes months. Two watch-list setups
fire about 15 times a month each. Tracking all three on paper, from the
moment tracking starts, turns "wait months" into "know in weeks" without
touching the demo account or loosening any gate.

Rules (fixed before tracking starts, never tuned on the tracked results):
- Signals, entries and exits are exactly the research rules: the signal is
  read on a closed candle, the entry is the next candle's open, the stop is
  ATR(14) x 2, the target ATR(14) x 4, at most 100 candles, and an opposite
  signal reverses the position. Costs are the research BASE costs.
- Only candles that close after tracking started count. Nothing is backfilled.
- Results are in R (multiples of the amount risked), so markets compare fairly.
- Nothing here places, changes or closes an order anywhere. A PASSED verdict
  only means "worth your decision"; it never enables trading by itself.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig, compute_stop_target_prices
from app.data_engine.market_data import Candle
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.crossover import detect_crossover_signals
from app.technical_engine.features import calculate_feature_snapshots
from app.technical_engine.indicators import calculate_sma
from app.technical_engine.models import TechnicalFeature

LIVE_EXIT = ExitConfig(
    label="live_atr2_tp4_max100",
    atr_stop_multiple=2.0,
    atr_take_profit_multiple=4.0,
    max_holding_candles=100,
)
# Research BASE costs in price units: (spread, slippage).
BASE_COSTS = {
    "EUR/USD": (0.00010, 0.00002),
    "GBP/USD": (0.00015, 0.00003),
    "USD/JPY": (0.012, 0.003),
    "XAU/USD": (0.35, 0.05),
}
TIMEFRAME_MINUTES = {"m15": 15, "h1": 60}
WARMUP_CANDLES = 300
MAX_CANDLES = 5000  # Deriv's per-request limit
DOLLARS_PER_R = 50.0  # 0.5% of a $10,000 account, the forward-test risk cap

FIRST_CHECKPOINT = 30
FINAL_CHECKPOINT = 60
PASS_RULE = (
    "Checked at 30 closed trades: profit factor 1.10 or better and a net gain passes; "
    "below 1.00 fails; anything in between keeps going to 60 trades, where 1.05 or better passes. "
    "A pass only means the setup has earned your decision. It never turns trading on by itself."
)


@dataclass(frozen=True)
class ShadowSetup:
    setup_id: str
    label: str
    instrument: str
    timeframe: str
    family: str  # "breakout" | "sma_crossover"
    param: int | tuple[int, int]
    role: str  # "forward_test" (allowed on demo) | "shadow" (paper only)
    why: str
    baseline: dict = field(default_factory=dict)


SETUPS: tuple[ShadowSetup, ...] = (
    ShadowSetup(
        setup_id="usdjpy_h1_breakout_55",
        label="USD/JPY H1 breakout (55)",
        instrument="USD/JPY",
        timeframe="h1",
        family="breakout",
        param=55,
        role="forward_test",
        why="Passed both the 2012-2022 test and the fresh 2026 data. The only setup allowed on the demo account.",
        baseline={"period": "Feb-Sep 2026", "trades": 47, "win_rate": 0.383, "profit_factor": 1.218, "per_month": 6},
    ),
    ShadowSetup(
        setup_id="eurusd_m15_sma_10_50",
        label="EUR/USD M15 trend (SMA 10/50)",
        instrument="EUR/USD",
        timeframe="m15",
        family="sma_crossover",
        param=(10, 50),
        role="shadow",
        why="Made money in both the 2025 and 2026 parts of the last 11 months, even at high costs, but lost on 2012-2022. Paper only.",
        baseline={"period": "Nov 2025-Sep 2026", "trades": 181, "win_rate": 0.42, "profit_factor": 1.349, "per_month": 16},
    ),
    ShadowSetup(
        setup_id="xauusd_m15_sma_10_50",
        label="Gold M15 trend (SMA 10/50)",
        instrument="XAU/USD",
        timeframe="m15",
        family="sma_crossover",
        param=(10, 50),
        role="shadow",
        why="Made money in both the 2025 and 2026 parts of the last 11 months, even at high costs, but lost on 2012-2022. Paper only.",
        baseline={"period": "Nov 2025-Sep 2026", "trades": 150, "win_rate": 0.413, "profit_factor": 1.273, "per_month": 14},
    ),
)
SETUPS_BY_ID = {s.setup_id: s for s in SETUPS}


def candle_step(timeframe: str) -> timedelta:
    return timedelta(minutes=TIMEFRAME_MINUTES[timeframe])


def floor_to_candle(moment: datetime, timeframe: str) -> datetime:
    minutes = TIMEFRAME_MINUTES[timeframe]
    base = moment.replace(second=0, microsecond=0)
    return base - timedelta(minutes=base.minute % minutes) if minutes < 60 else base.replace(minute=0)


def completed_candles(candles: list[Candle], timeframe: str, now: datetime) -> list[Candle]:
    step = candle_step(timeframe)
    return [c for c in candles if c.timestamp + step <= now]


def candles_needed(anchor: datetime, timeframe: str, now: datetime) -> int:
    span = int((now - anchor) / candle_step(timeframe)) + 2
    return min(MAX_CANDLES, WARMUP_CANDLES + max(span, 0))


def _signals(setup: ShadowSetup, candles: list[Candle]):
    if setup.family == "breakout":
        return detect_breakout_signals(candles, lookback=int(setup.param), symbol=setup.instrument)
    fast, slow = setup.param  # type: ignore[misc]
    closes = [c.close for c in candles]
    f, s = calculate_sma(closes, period=fast), calculate_sma(closes, period=slow)
    features = [TechnicalFeature(timestamp=c.timestamp, close=c.close, sma_10=f[i], sma_50=s[i]) for i, c in enumerate(candles)]
    return detect_crossover_signals(features, symbol=setup.instrument)


@dataclass
class ReplayResult:
    closed: list[dict]
    open_trade: dict | None
    new_anchor: datetime
    last_candle_at: datetime | None


def _direction(trade_direction: str) -> str:
    return "BUY" if trade_direction == "LONG" else "SELL"


def replay(setup: ShadowSetup, candles: list[Candle], anchor: datetime) -> ReplayResult:
    """Run the research simulator over completed candles, counting signals from `anchor` on.

    The state is known to be flat before `anchor` (it is either the tracking
    start or the signal candle of the position that is still open), so this
    reproduces exactly what one continuous run would have produced.
    """
    if not candles:
        return ReplayResult([], None, anchor, None)
    features = calculate_feature_snapshots(candles)
    signals = [
        s if s.timestamp >= anchor else replace(s, direction="WAIT", reason="Before tracking started.")
        for s in _signals(setup, candles)
    ]
    spread, slippage = BASE_COSTS[setup.instrument]
    size = 10_000.0 * 1.18 / statistics.fmean(c.close for c in candles)
    config = BacktestConfig(
        symbol=setup.instrument, timeframe=setup.timeframe, initial_balance=10_000.0,
        position_size=size, spread=spread, slippage=slippage,
    )
    result = simulate_trades_with_exit_rules(candles, signals, features, config, LIVE_EXIT)
    index_of = {c.timestamp: i for i, c in enumerate(candles)}

    def describe(trade) -> dict:
        i = index_of[trade.entry_timestamp]
        entry_mid = candles[i].open
        stop, target = compute_stop_target_prices(
            direction=trade.direction, entry_price=entry_mid,
            entry_atr_14=features[i].atr_14, exit_config=LIVE_EXIT,
        )
        risk = abs(entry_mid - stop) * trade.size if stop is not None else 0.0
        return {
            "setup_id": setup.setup_id,
            "instrument": setup.instrument,
            "timeframe": setup.timeframe,
            "direction": _direction(trade.direction),
            "signal_at": trade.signal_timestamp,
            "entry_at": trade.entry_timestamp,
            "entry_price": entry_mid,
            "stop_price": stop,
            "target_price": target,
            "exit_at": trade.exit_timestamp,
            "exit_price": trade.exit_price,
            "exit_reason": _reason(trade.exit_reason),
            "r_multiple": round(trade.net_pnl / risk, 3) if risk > 0 else 0.0,
        }

    closed, open_trade = [], None
    for trade in result.trades:
        if trade.signal_timestamp < anchor:
            continue
        if trade.exit_reason == "END_OF_DATA":
            open_trade = describe(trade)
            open_trade.update(exit_at=None, exit_reason=None, mark_price=candles[-1].close,
                              open_r=open_trade.pop("r_multiple"))
            open_trade.pop("exit_price")
        else:
            closed.append(describe(trade))

    last = candles[-1]
    if open_trade is not None:
        new_anchor = open_trade["signal_at"]
    else:
        # Flat at the end: resume from the last candle (its own signal, if
        # any, is pending and will be re-read next time).
        new_anchor = max(anchor, last.timestamp)
    return ReplayResult(closed, open_trade, new_anchor, last.timestamp)


def _reason(raw: str) -> str:
    if raw == "STOP_LOSS":
        return "Stop loss"
    if raw == "TAKE_PROFIT":
        return "Take profit"
    if raw == "MAX_HOLDING_PERIOD":
        return "Time limit (100 candles)"
    if raw.startswith("Reversed"):
        return "Reversed by opposite signal"
    return raw


def score(r_multiples: list[float]) -> dict:
    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r <= 0]
    gains, pains = sum(wins), -sum(losses)
    streak = worst_streak = 0
    for r in r_multiples:
        streak = streak + 1 if r <= 0 else 0
        worst_streak = max(worst_streak, streak)
    return {
        "trades": len(r_multiples),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(r_multiples), 3) if r_multiples else None,
        # None when there is no loss yet (JSON has no infinity).
        "profit_factor": round(gains / pains, 3) if pains > 0 else None,
        "net_r": round(sum(r_multiples), 2),
        "net_usd_at_50_per_r": round(sum(r_multiples) * DOLLARS_PER_R, 2),
        "avg_win_r": round(statistics.fmean(wins), 2) if wins else None,
        "avg_loss_r": round(statistics.fmean(losses), 2) if losses else None,
        "longest_losing_streak": worst_streak,
    }


def _pf(r_multiples: list[float]) -> float:
    gains = sum(r for r in r_multiples if r > 0)
    pains = -sum(r for r in r_multiples if r <= 0)
    if pains > 0:
        return gains / pains
    return 99.0 if gains > 0 else 0.0


def verdict(r_multiples: list[float]) -> dict:
    """Apply the pre-registered pass mark (PASS_RULE) to trades in the order they closed."""
    n = len(r_multiples)
    if n < FIRST_CHECKPOINT:
        return {"state": "COLLECTING", "target": FIRST_CHECKPOINT,
                "message": f"{n} of {FIRST_CHECKPOINT} trades so far. Too early to judge."}
    first = r_multiples[:FIRST_CHECKPOINT]
    first_pf = _pf(first)
    if first_pf >= 1.10 and sum(first) > 0:
        return {"state": "PASSED", "target": FIRST_CHECKPOINT,
                "message": f"Passed at {FIRST_CHECKPOINT} trades (profit factor {first_pf:.2f}). Your call whether it earns the demo account."}
    if first_pf < 1.00:
        return {"state": "FAILED", "target": FIRST_CHECKPOINT,
                "message": f"Failed at {FIRST_CHECKPOINT} trades (profit factor {first_pf:.2f}). Drop it."}
    if n < FINAL_CHECKPOINT:
        return {"state": "EXTENDED", "target": FINAL_CHECKPOINT,
                "message": f"Borderline at {FIRST_CHECKPOINT} trades (profit factor {first_pf:.2f}), so it runs to {FINAL_CHECKPOINT}. {n} so far."}
    final_pf = _pf(r_multiples[:FINAL_CHECKPOINT])
    if final_pf >= 1.05:
        return {"state": "PASSED", "target": FINAL_CHECKPOINT,
                "message": f"Passed at {FINAL_CHECKPOINT} trades (profit factor {final_pf:.2f}). Your call whether it earns the demo account."}
    return {"state": "FAILED", "target": FINAL_CHECKPOINT,
            "message": f"Failed at {FINAL_CHECKPOINT} trades (profit factor {final_pf:.2f}). Drop it."}
