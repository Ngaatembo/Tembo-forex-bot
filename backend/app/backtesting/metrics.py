"""
Computes BacktestSummary from a completed trade list and equity curve.

Every ratio-based statistic returns None rather than a fabricated or
divide-by-zero value when there isn't enough data to compute it
meaningfully — zero trades means zero trades, not a 0% win rate or an
infinite profit factor.
"""

from app.backtesting.models import BacktestSummary, EquityPoint, Trade


def compute_metrics(
    trades: list[Trade], equity_curve: list[EquityPoint], initial_balance: float
) -> BacktestSummary:
    net_pnl = sum(t.net_pnl for t in trades)
    final_balance = initial_balance + net_pnl
    total_return = net_pnl / initial_balance

    summary = BacktestSummary(
        initial_balance=initial_balance,
        final_balance=final_balance,
        net_pnl=net_pnl,
        total_return=total_return,
        trade_count=len(trades),
    )

    if equity_curve:
        summary.max_drawdown = max(p.drawdown for p in equity_curve)
        summary.max_drawdown_percent = max(p.drawdown_percent for p in equity_curve)

    if not trades:
        return summary  # every trade-dependent stat stays None — no fabricated numbers

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]

    summary.winning_trades = len(wins)
    summary.losing_trades = len(losses)
    summary.win_rate = len(wins) / len(trades)
    summary.average_trade = net_pnl / len(trades)
    summary.expectancy = summary.average_trade  # same figure, standard alternate name

    if wins:
        summary.average_win = sum(t.net_pnl for t in wins) / len(wins)
        summary.largest_win = max(t.net_pnl for t in wins)
    if losses:
        summary.average_loss = sum(t.net_pnl for t in losses) / len(losses)
        summary.largest_loss = min(t.net_pnl for t in losses)

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    # profit_factor is undefined (not infinite) with zero losing trades —
    # reported as None rather than a misleading "infinite edge" figure.
    summary.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    summary.max_consecutive_wins = _max_streak(trades, lambda t: t.net_pnl > 0)
    summary.max_consecutive_losses = _max_streak(trades, lambda t: t.net_pnl < 0)

    return summary


def _max_streak(trades: list[Trade], predicate) -> int:
    best = current = 0
    for t in trades:
        if predicate(t):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best
