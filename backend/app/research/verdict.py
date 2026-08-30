"""
Deterministic verdict engine.

Turns three periods' worth of BacktestSummary into ONE evidence-based
verdict. This is a simple, documented, DETERMINISTIC heuristic — not
an LLM, not a scientific proof, not a guarantee. The thresholds below
(MIN_TRADES, DEGRADATION_THRESHOLD) were chosen once, for this
document, before running any real experiment in this phase — they are
not tuned to make any particular hypothesis look better or worse.

VALIDATED_FOR_PAPER_TRADING is never assigned automatically by this
function — see its docstring below for why.
"""

from enum import Enum

from app.backtesting.models import BacktestSummary

MIN_TRADES_PER_PERIOD = 10
DEGRADATION_THRESHOLD = 0.5  # oos profit factor losing >50% of dev's edge over 1.0 is "suspicious"


class Verdict(str, Enum):
    UNTESTED = "UNTESTED"
    PROMISING = "PROMISING"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED = "REJECTED"
    OVERFIT_SUSPECTED = "OVERFIT_SUSPECTED"
    OUT_OF_SAMPLE_FAILED = "OUT_OF_SAMPLE_FAILED"
    VALIDATED_FOR_PAPER_TRADING = "VALIDATED_FOR_PAPER_TRADING"


def compute_verdict(
    development: BacktestSummary, validation: BacktestSummary, out_of_sample: BacktestSummary,
    min_trades: int = MIN_TRADES_PER_PERIOD, degradation_threshold: float = DEGRADATION_THRESHOLD,
) -> Verdict:
    """
    Decision rules, in order:

    1. INCONCLUSIVE — any period has fewer than `min_trades` trades.
       Not enough evidence to say anything at all, in either direction.
    2. REJECTED — development profit_factor <= 1.0. The hypothesis
       didn't even work on the data it was built to fit; there's no
       reason to look further.
    3. OUT_OF_SAMPLE_FAILED — development worked (profit_factor > 1.0)
       but out_of_sample did not (<= 1.0). The classic "looked good in
       development, failed on unseen data" pattern.
    4. OVERFIT_SUSPECTED — development AND out_of_sample both show
       profit_factor > 1.0, but EITHER validation doesn't, OR
       out_of_sample's edge has degraded more than
       `degradation_threshold` relative to development's. Passing dev
       and oos while failing the middle period, or a large edge
       collapse, are both signs of an inconsistent, fragile pattern
       rather than a real one.
    5. PROMISING — profit_factor > 1.0 in all three periods, with
       degradation below the threshold. This means "worth continued
       research" — it does NOT mean "ready for real money."

    VALIDATED_FOR_PAPER_TRADING is intentionally NEVER returned by this
    function. It represents a decision that this evidence is strong
    enough to risk-manage into a paper account — that is a human (or a
    later, separately-designed, more conservative process) decision,
    not something a single heuristic function should auto-grant.
    """
    periods = {"development": development, "validation": validation, "out_of_sample": out_of_sample}
    for label, summary in periods.items():
        if summary.trade_count < min_trades:
            return Verdict.INCONCLUSIVE

    dev_pf = development.profit_factor or 0.0
    val_pf = validation.profit_factor or 0.0
    oos_pf = out_of_sample.profit_factor or 0.0

    if dev_pf <= 1.0:
        return Verdict.REJECTED

    if oos_pf <= 1.0:
        return Verdict.OUT_OF_SAMPLE_FAILED

    degradation = (dev_pf - oos_pf) / dev_pf if dev_pf > 0 else 1.0
    if val_pf <= 1.0 or degradation > degradation_threshold:
        return Verdict.OVERFIT_SUSPECTED

    return Verdict.PROMISING
