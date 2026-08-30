"""
Generic historical-CSV importer.

This module ONLY parses raw file rows into Candle objects. It does
NOT normalize (UTC/dedup/sort) or validate (OHLC sanity/gaps) — those
responsibilities stay exactly where Phase 1 already put them
(app.data_engine.normalizer, app.data_engine.validator). Any imported
dataset, from any source, must be run through both of those before
being trusted, exactly like OANDA data is.

REQUIRED INPUT FORMAT (the contract any CSV source must satisfy,
either natively or via a small adapter — see importers/ejtrader_source.py
for a worked example adapter):

    A CSV file with a header row and at least these columns (names
    configurable via CSVImportConfig, since real-world exports vary):
        - a timestamp column, parseable by pandas.to_datetime
        - open, high, low, close price columns, in REAL PRICE UNITS
          (e.g. 1.09500 for EUR/USD — not broker-internal scaled
          integers; use `price_scale` to convert if the source uses
          a different convention)
        - optionally a volume column

    Timezone: if the source's timestamps are not explicitly UTC, the
    caller MUST set `assumed_timezone` and this MUST be documented in
    the resulting dataset's metadata (see importers/ejtrader_source.py
    for why this matters and what we do when a source doesn't say).
"""

from dataclasses import dataclass
from datetime import timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from app.data_engine.market_data import Candle


@dataclass
class CSVImportConfig:
    timestamp_column: str
    open_column: str
    high_column: str
    low_column: str
    close_column: str
    volume_column: Optional[str] = None
    price_scale: float = 1.0  # multiply raw price columns by this to get real price units
    assumed_timezone: str = "UTC"  # IANA name; documented assumption if not confirmed by the source


def import_candles_from_csv(
    path: str, *, symbol: str, timeframe: str, config: CSVImportConfig
) -> list[Candle]:
    df = pd.read_csv(path)

    required = [
        config.timestamp_column, config.open_column, config.high_column,
        config.low_column, config.close_column,
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV at {path} is missing required column(s): {missing}")

    tz = ZoneInfo(config.assumed_timezone) if config.assumed_timezone != "UTC" else timezone.utc

    candles: list[Candle] = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row[config.timestamp_column])
        if ts.tzinfo is None:
            ts = ts.tz_localize(tz)
        ts = ts.to_pydatetime().astimezone(timezone.utc)

        volume = float(row[config.volume_column]) if config.volume_column else None

        candles.append(
            Candle(
                symbol=symbol, timeframe=timeframe, timestamp=ts,
                open=float(row[config.open_column]) * config.price_scale,
                high=float(row[config.high_column]) * config.price_scale,
                low=float(row[config.low_column]) * config.price_scale,
                close=float(row[config.close_column]) * config.price_scale,
                volume=volume,
            )
        )
    return candles
