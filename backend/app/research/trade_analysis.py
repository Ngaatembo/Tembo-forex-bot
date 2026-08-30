"""
Descriptive research analysis: joins the baseline strategy's already-
completed trades (Phase 4/4.5, unmodified) with the technical/regime
context that existed at signal time (Phase 5's feature layer), then
reports observed outcomes grouped by condition.

TIMING RULE (Phase 5 spec section 16): every trade is joined to the
FeatureSnapshot at its `signal_timestamp`, never its `entry_timestamp`.
The execution model (Phase 4) always executes one candle AFTER the
signal candle — using entry-time features would leak one candle of
hindsight into "what did we know when we decided to trade," which is
exactly the kind of subtle lookahead this project has been careful to
avoid everywhere else.

INTERPRETATION DISCIPLINE — this module ONLY computes descriptive
statistics on already-completed history. It:
  - never changes the strategy or its trades
  - never excludes or cherry-picks trades
  - never computes a "recommended" threshold or rule
  - never claims a correlation is a cause
Any interesting pattern found here belongs in a HYPOTHESIS list for
later out-of-sample testing — see docs/phase-5-notes.md — not directly
in a trading rule.

A note on "drawdown" for a grouped subset: the trades within one
regime/RSI bucket do NOT form a real, standalone tradable equity
curve (they're interleaved with trades from other buckets in the
actual account). So this module reports each subset's cumulative P&L
peak-to-trough as an approximate, clearly-labeled figure — not the
same thing as the real portfolio-level max_drawdown computed in
Phase 4.
"""

from dataclasses import dataclass

from app.backtesting.models import Trade
from app.technical_engine.models import FeatureSnapshot


@dataclass
class TradeContext:
    trade: Trade
    features: FeatureSnapshot | None  # None if no snapshot exists at signal_timestamp


@dataclass
class ConditionStats:
    condition_label: str
    trade_count: int
    winning_trades: int | None = None
    losing_trades: int | None = None
    win_rate: float | None = None
    net_pnl: float = 0.0
    average_trade: float | None = None
    profit_factor: float | None = None
    largest_win: float | None = None
    largest_loss: float | None = None
    approx_subset_max_drawdown: float | None = None  # see module docstring caveat


def attach_context_to_trades(
    trades: list[Trade], features: list[FeatureSnapshot]
) -> list[TradeContext]:
    features_by_timestamp = {f.timestamp: f for f in features}
    return [
        TradeContext(trade=t, features=features_by_timestamp.get(t.signal_timestamp))
        for t in trades
    ]


def _compute_condition_stats(label: str, trades: list[Trade]) -> ConditionStats:
    stats = ConditionStats(condition_label=label, trade_count=len(trades))
    if not trades:
        return stats

    stats.net_pnl = sum(t.net_pnl for t in trades)
    stats.average_trade = stats.net_pnl / len(trades)

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    stats.winning_trades = len(wins)
    stats.losing_trades = len(losses)
    stats.win_rate = len(wins) / len(trades)

    if wins:
        stats.largest_win = max(t.net_pnl for t in wins)
    if losses:
        stats.largest_loss = min(t.net_pnl for t in losses)

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    stats.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    # Approximate subset drawdown: cumulative P&L path of just this
    # subset's trades, in their original chronological order. NOT a
    # real portfolio equity curve — see module docstring.
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda t: t.entry_timestamp):
        cumulative += t.net_pnl
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    stats.approx_subset_max_drawdown = max_dd

    return stats


def group_by_regime(contexts: list[TradeContext]) -> dict[str, ConditionStats]:
    buckets: dict[str, list[Trade]] = {}
    for ctx in contexts:
        label = ctx.features.regime if ctx.features is not None else "NO_FEATURE_DATA"
        buckets.setdefault(label, []).append(ctx.trade)
    return {label: _compute_condition_stats(label, trades) for label, trades in buckets.items()}


def _rsi_zone(rsi: float | None) -> str:
    if rsi is None:
        return "unknown"
    if rsi < 30:
        return "RSI<30"
    if rsi < 50:
        return "RSI 30-50"
    if rsi < 70:
        return "RSI 50-70"
    return "RSI>=70"


def group_by_rsi_zone(contexts: list[TradeContext]) -> dict[str, ConditionStats]:
    buckets: dict[str, list[Trade]] = {}
    for ctx in contexts:
        rsi = ctx.features.rsi_14 if ctx.features is not None else None
        label = _rsi_zone(rsi)
        buckets.setdefault(label, []).append(ctx.trade)
    return {label: _compute_condition_stats(label, trades) for label, trades in buckets.items()}
