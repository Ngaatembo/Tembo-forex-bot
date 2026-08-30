"""
Development / validation / out-of-sample period definitions, with
strict chronological enforcement — overlapping or reversed periods are
rejected at construction time, not discovered later as a silent bug.
"""

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class EvaluationPeriod:
    label: str  # "development" | "validation" | "out_of_sample"
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError(f"{self.label}: start ({self.start}) must be before end ({self.end}).")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        return d


@dataclass(frozen=True)
class EvaluationPeriods:
    development: EvaluationPeriod
    validation: EvaluationPeriod
    out_of_sample: EvaluationPeriod

    def __post_init__(self):
        periods = [self.development, self.validation, self.out_of_sample]
        for a, b in zip(periods, periods[1:]):
            if a.end > b.start:
                raise ValueError(
                    f"Periods must be strictly chronological and non-overlapping: "
                    f"{a.label} ends {a.end} but {b.label} starts {b.start}."
                )

    def to_dict(self) -> dict:
        return {
            "development": self.development.to_dict(),
            "validation": self.validation.to_dict(),
            "out_of_sample": self.out_of_sample.to_dict(),
        }


def split_candles_by_period(candles: list, periods: EvaluationPeriods) -> dict:
    """Splits an already-sorted candle list into three slices by timestamp."""
    return {
        "development": [c for c in candles if periods.development.start <= c.timestamp < periods.development.end],
        "validation": [c for c in candles if periods.validation.start <= c.timestamp < periods.validation.end],
        "out_of_sample": [c for c in candles if periods.out_of_sample.start <= c.timestamp < periods.out_of_sample.end],
    }
