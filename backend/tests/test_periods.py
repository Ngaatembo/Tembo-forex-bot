from datetime import datetime, timezone

import pytest

from app.data_engine.market_data import Candle
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period


def dt(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=timezone.utc)


def test_period_rejects_start_after_end():
    with pytest.raises(ValueError, match="must be before"):
        EvaluationPeriod(label="development", start=dt(10), end=dt(5))


def test_periods_reject_overlap():
    dev = EvaluationPeriod("development", dt(1), dt(10))
    val = EvaluationPeriod("validation", dt(5), dt(15))  # overlaps dev
    oos = EvaluationPeriod("out_of_sample", dt(15), dt(20))
    with pytest.raises(ValueError, match="chronological"):
        EvaluationPeriods(development=dev, validation=val, out_of_sample=oos)


def test_periods_reject_reversed_order():
    dev = EvaluationPeriod("development", dt(10), dt(20))
    val = EvaluationPeriod("validation", dt(1), dt(9))  # before dev — reversed
    oos = EvaluationPeriod("out_of_sample", dt(21), dt(25))
    with pytest.raises(ValueError, match="chronological"):
        EvaluationPeriods(development=dev, validation=val, out_of_sample=oos)


def test_valid_chronological_periods_accepted():
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", dt(1), dt(10)),
        validation=EvaluationPeriod("validation", dt(10), dt(15)),
        out_of_sample=EvaluationPeriod("out_of_sample", dt(15), dt(20)),
    )
    assert periods.development.start == dt(1)


def test_split_candles_by_period():
    candles = [
        Candle("EUR/USD", "1h", dt(2), 1.1, 1.1, 1.1, 1.1, 100),
        Candle("EUR/USD", "1h", dt(11), 1.1, 1.1, 1.1, 1.1, 100),
        Candle("EUR/USD", "1h", dt(16), 1.1, 1.1, 1.1, 1.1, 100),
    ]
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", dt(1), dt(10)),
        validation=EvaluationPeriod("validation", dt(10), dt(15)),
        out_of_sample=EvaluationPeriod("out_of_sample", dt(15), dt(20)),
    )
    split = split_candles_by_period(candles, periods)
    assert len(split["development"]) == 1
    assert len(split["validation"]) == 1
    assert len(split["out_of_sample"]) == 1
