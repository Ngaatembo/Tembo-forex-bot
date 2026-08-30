"""
Basic overfitting diagnostics.

THIS IS A DIAGNOSTIC AID, NOT A DETECTOR. It flags patterns that are
COMMONLY ASSOCIATED with overfitting so a human reviewer looks closer
— it cannot prove overfitting happened, and a clean diagnostic report
does not prove a hypothesis is robust. Every threshold here is a
documented, arbitrary starting choice, same as regime.py's thresholds
in Phase 5 — never tuned against any hypothesis's actual results.
"""

from dataclasses import dataclass

from app.backtesting.models import BacktestSummary

LOW_TRADE_COUNT_THRESHOLD = 30
LARGE_DEGRADATION_THRESHOLD = 0.5


@dataclass
class OverfittingDiagnostics:
    low_trade_count_development: bool
    low_trade_count_validation: bool
    low_trade_count_out_of_sample: bool
    development_return: float
    validation_return: float
    out_of_sample_return: float
    development_to_oos_pf_degradation: float | None  # None if dev profit_factor is None/0
    strong_dev_then_oos_failure: bool  # dev clearly profitable, oos clearly not
    any_flag_raised: bool


def compute_overfitting_diagnostics(
    development: BacktestSummary, validation: BacktestSummary, out_of_sample: BacktestSummary,
) -> OverfittingDiagnostics:
    low_dev = development.trade_count < LOW_TRADE_COUNT_THRESHOLD
    low_val = validation.trade_count < LOW_TRADE_COUNT_THRESHOLD
    low_oos = out_of_sample.trade_count < LOW_TRADE_COUNT_THRESHOLD

    dev_pf = development.profit_factor
    oos_pf = out_of_sample.profit_factor
    degradation = ((dev_pf - oos_pf) / dev_pf) if dev_pf else None

    strong_dev_then_failure = bool(dev_pf and dev_pf > 1.2 and (oos_pf is None or oos_pf <= 1.0))

    any_flag = (
        low_dev or low_val or low_oos or strong_dev_then_failure
        or (degradation is not None and degradation > LARGE_DEGRADATION_THRESHOLD)
    )

    return OverfittingDiagnostics(
        low_trade_count_development=low_dev,
        low_trade_count_validation=low_val,
        low_trade_count_out_of_sample=low_oos,
        development_return=development.total_return,
        validation_return=validation.total_return,
        out_of_sample_return=out_of_sample.total_return,
        development_to_oos_pf_degradation=degradation,
        strong_dev_then_oos_failure=strong_dev_then_failure,
        any_flag_raised=any_flag,
    )
