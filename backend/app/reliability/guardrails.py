"""Reliability and robustness gates for Tembo.

This module is deliberately pure and side-effect free. It does not place
orders, mutate accounts, or learn parameters from live outcomes.
"""

from dataclasses import dataclass
from math import isfinite
from statistics import mean
import random


@dataclass(frozen=True)
class CostGateResult:
    status: str
    reason: str
    cost_to_target_ratio: float | None


def evaluate_cost_gate(
    entry: float,
    stop_loss: float,
    take_profit: float,
    estimated_cost: float,
    max_cost_to_target: float = 0.20,
) -> CostGateResult:
    if not all(isfinite(x) for x in (entry, stop_loss, take_profit, estimated_cost)):
        return CostGateResult("BLOCK", "NON_FINITE_EXECUTION_INPUT", None)
    target_distance = abs(take_profit - entry)
    if target_distance <= 0 or estimated_cost < 0:
        return CostGateResult("BLOCK", "INVALID_COST_OR_TARGET", None)
    ratio = estimated_cost / target_distance
    if ratio > max_cost_to_target:
        return CostGateResult("BLOCK", "EXECUTION_COST_TOO_LARGE_FOR_TARGET", ratio)
    return CostGateResult("PASS", "EXECUTION_COST_WITHIN_BOUND", ratio)


@dataclass(frozen=True)
class DrawdownGovernorResult:
    status: str
    size_multiplier: float
    reason: str


def drawdown_governor(
    drawdown_pct: float,
    warning_pct: float = 5.0,
    severe_pct: float = 10.0,
    halt_pct: float = 15.0,
) -> DrawdownGovernorResult:
    if not isfinite(drawdown_pct) or drawdown_pct < 0:
        return DrawdownGovernorResult("HALT", 0.0, "INVALID_DRAWDOWN")
    if drawdown_pct >= halt_pct:
        return DrawdownGovernorResult("HALT", 0.0, "DRAWDOWN_HALT")
    if drawdown_pct >= severe_pct:
        return DrawdownGovernorResult("SEVERE", 0.25, "DRAWDOWN_SEVERE")
    if drawdown_pct >= warning_pct:
        return DrawdownGovernorResult("WARNING", 0.50, "DRAWDOWN_WARNING")
    return DrawdownGovernorResult("NORMAL", 1.0, "DRAWDOWN_NORMAL")


@dataclass(frozen=True)
class DriftResult:
    status: str
    baseline_mean: float
    live_mean: float
    difference: float
    reason: str


def detect_drift(
    baseline: list[float],
    live: list[float],
    tolerance: float = 0.15,
) -> DriftResult:
    if len(baseline) < 10 or len(live) < 10:
        return DriftResult("INSUFFICIENT_DATA", 0.0, 0.0, 0.0, "NEED_10_OBSERVATIONS_PER_WINDOW")
    if not all(isfinite(x) for x in baseline + live):
        return DriftResult("BLOCK", 0.0, 0.0, 0.0, "NON_FINITE_OBSERVATION")
    bm, lm = mean(baseline), mean(live)
    difference = lm - bm
    scale = max(abs(bm), 1e-9)
    relative = abs(difference) / scale
    if relative >= tolerance:
        return DriftResult("DRIFT", bm, lm, difference, "LIVE_BEHAVIOUR_DEVIATES_FROM_BASELINE")
    return DriftResult("STABLE", bm, lm, difference, "NO_MATERIAL_DRIFT")


@dataclass(frozen=True)
class MonteCarloResult:
    simulations: int
    worst_return: float
    median_return: float
    loss_probability: float


def monte_carlo_trade_resample(
    returns: list[float],
    simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    if not returns or simulations < 100:
        return MonteCarloResult(0, 0.0, 0.0, 0.0)
    clean = [x for x in returns if isfinite(x)]
    if len(clean) < 20:
        return MonteCarloResult(0, 0.0, 0.0, 0.0)
    rng = random.Random(seed)
    outcomes: list[float] = []
    for _ in range(simulations):
        outcomes.append(sum(rng.choice(clean) for _ in clean))
    outcomes.sort()
    losses = sum(x < 0 for x in outcomes)
    return MonteCarloResult(
        simulations=len(outcomes),
        worst_return=outcomes[0],
        median_return=outcomes[len(outcomes) // 2],
        loss_probability=losses / len(outcomes),
    )
