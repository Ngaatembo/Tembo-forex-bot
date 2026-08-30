"""
Dataset identification/versioning — every experiment must record
exactly which dataset produced its results, so two experiments are
never accidentally compared across different data.
"""

import hashlib
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str          # e.g. "EURUSD_1H_2012_2022_v1"
    source: str
    license: str
    symbol: str
    timeframe: str
    period_start: str
    period_end: str
    candle_count: int
    import_version: str
    sha256: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_dataset_id(symbol: str, timeframe: str, start_year: int, end_year: int, version: int = 1) -> str:
    clean_symbol = symbol.replace("/", "")
    return f"{clean_symbol}_{timeframe.upper()}_{start_year}_{end_year}_v{version}"


def compute_file_sha256(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
