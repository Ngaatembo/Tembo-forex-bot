"""
Statistical diagnostics for a completed trade list. Pure functions,
no database/broker/execution access, no dependency on verdict.py or
baseline.py — these are read-only analysis tools that CANNOT change
any recorded verdict; they only describe evidence already produced by
the (unmodified) backtesting engine.

LIMITATION, stated once here and referenced everywhere these are used:
the bootstrap confidence interval below resamples trades as if they
were independent draws. Real trades from the same strategy are not
fully independent (consecutive trades can share market conditions,
and losing streaks can cluster) — this is a standard simplification
in trading research, not a claim of statistical purity. Treat the
resulting interval as indicative, not as a rigorous i.i.d. guarantee.

A second, smaller limitation discovered while testing this module:
with a very small number of distinct trade P&L values, the resampled
sums only take a small number of distinct discrete values, so the
reported interval boundary can occasionally coincide even across
different random seeds — verified during testing to be a genuine
property of small/discrete samples, not an RNG bug (the full
underlying resampled distributions do differ). With H1's real
out-of-sample sample size (253 trades), this is not expected to be
a practical concern — noted here because it's the kind of thing worth
checking, not assuming, exactly like everything else in this project.
"""

import random
from dataclasses import dataclass

from app.backtesting.models import Trade


@dataclass
class PayoffStats:
    average_win: float | None
    average_loss: float | None  # negative, or None if no losses
    largest_win: float | None
    largest_loss: float | None
    payoff_ratio: float | None  # average_win / abs(average_loss); None if no losses


def compute_payoff_stats(trades: list[Trade]) -> PayoffStats:
    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl < 0]

    average_win = sum(wins) / len(wins) if wins else None
    average_loss = sum(losses) / len(losses) if losses else None
    largest_win = max(wins) if wins else None
    largest_loss = min(losses) if losses else None
    payoff_ratio = (average_win / abs(average_loss)) if (wins and losses) else None

    return PayoffStats(
        average_win=average_win, average_loss=average_loss,
        largest_win=largest_win, largest_loss=largest_loss, payoff_ratio=payoff_ratio,
    )


def compute_breakeven_win_rate(payoff_ratio: float | None) -> float | None:
    """
    The win rate needed just to break even, given the payoff ratio R
    (average win / average loss size): breakeven_rate = 1 / (1 + R).

    A payoff_ratio of None (no losses recorded, or no wins) makes a
    breakeven rate undefined — returns None rather than a misleading number.
    """
    if payoff_ratio is None or payoff_ratio <= 0:
        return None
    return 1.0 / (1.0 + payoff_ratio)


def wilson_confidence_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float] | None:
    """
    Wilson score interval for a binomial proportion (here: win rate).
    More reliable than a naive normal-approximation interval at
    moderate sample sizes, which is why it's the standard choice for
    reporting a win-rate confidence range in trading research.

    Returns None for n == 0. Only the 95% confidence level (z=1.96) is
    implemented — documented, not silently assumed for other levels.
    """
    if n == 0:
        return None
    if confidence != 0.95:
        raise NotImplementedError("Only the 95% confidence level (z=1.96) is implemented.")

    z = 1.959963985
    p_hat = successes / n
    denominator = 1 + (z ** 2) / n
    center = (p_hat + (z ** 2) / (2 * n)) / denominator
    margin = (z * ((p_hat * (1 - p_hat) + (z ** 2) / (4 * n)) / n) ** 0.5) / denominator

    return (max(0.0, center - margin), min(1.0, center + margin))


def bootstrap_pnl_confidence_interval(
    trade_pnls: list[float], n_resamples: int = 10_000, confidence: float = 0.95, seed: int = 42
) -> tuple[float, float] | None:
    """
    Resamples the trade P&L list WITH REPLACEMENT `n_resamples` times
    (each resample the same size as the original), sums each resample,
    and reports the percentile range of those sums as a confidence
    interval on total P&L.

    See module docstring for the independence-assumption limitation.
    `seed` is fixed for reproducibility — the same trade list always
    produces the exact same interval, never a different one on rerun.
    """
    if not trade_pnls:
        return None
    if confidence != 0.95:
        raise NotImplementedError("Only the 95% confidence level is implemented.")

    rng = random.Random(seed)
    n = len(trade_pnls)
    resampled_totals = []
    for _ in range(n_resamples):
        resample = [trade_pnls[rng.randrange(n)] for _ in range(n)]
        resampled_totals.append(sum(resample))

    resampled_totals.sort()
    low_idx = int(0.025 * n_resamples)
    high_idx = int(0.975 * n_resamples) - 1
    return (resampled_totals[low_idx], resampled_totals[high_idx])
