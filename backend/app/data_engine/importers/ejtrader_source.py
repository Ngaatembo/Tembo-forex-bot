"""
Adapter for the ejtraderLabs/historical-data GitHub repository
(https://github.com/ejtraderLabs/historical-data, Apache-2.0 license).

DATASET METADATA (fill in per file used — see docs/phase-4-5-real-historical-validation.md
for the exact values recorded for this validation run):

    Source:      https://github.com/ejtraderLabs/historical-data
    File used:   EURUSD/EURUSDh1.csv (fetched via raw.githubusercontent.com)
    License:     Apache-2.0
    Format:      Date,open,high,low,close,tick_volume — prices scaled x100000
                 (an MT4/MetaTrader-style export convention: 127801 means 1.27801)
    Timezone:    NOT documented by the source. This is a real, honestly-reported
                 limitation — see the KNOWN LIMITATION note below.

KNOWN LIMITATION — timezone assumption:
    The source repository does not state what timezone its timestamps
    are in. MT4-style exports are very commonly in the broker's server
    time (often UTC+2 or UTC+3, sometimes with its own DST rules) —
    NOT plain UTC. We could not independently verify this without a
    second labeled source to cross-check against, which we don't have
    in this environment. We treat the timestamps AS-IS, labeled UTC,
    without a timezone shift applied. If the true offset is a few
    hours, this Phase 4.5 validation's exact trade entry/exit HOURS
    could be shifted correspondingly — the overall shape of the
    result (trade count, direction of edge, drawdown) is not sensitive
    to a small constant hour-shift, but exact timestamps should not be
    treated as broker-server-time-accurate. This should be resolved
    before any conclusion here is used for real decisions.
"""

from app.data_engine.importers.csv_importer import CSVImportConfig, import_candles_from_csv
from app.data_engine.market_data import Candle

EJTRADER_SOURCE_URL = "https://github.com/ejtraderLabs/historical-data"
EJTRADER_LICENSE = "Apache-2.0"

# 100000 -> divide by 100000 to get real price units (127801 -> 1.27801)
EJTRADER_PRICE_SCALE = 1 / 100_000


def ejtrader_import_config() -> CSVImportConfig:
    return CSVImportConfig(
        timestamp_column="Date",
        open_column="open", high_column="high", low_column="low", close_column="close",
        volume_column="tick_volume",
        price_scale=EJTRADER_PRICE_SCALE,
        assumed_timezone="UTC",  # see module docstring — not confirmed by the source
    )


def import_ejtrader_eurusd_h1(path: str) -> list[Candle]:
    return import_candles_from_csv(
        path, symbol="EUR/USD", timeframe="1h", config=ejtrader_import_config()
    )
