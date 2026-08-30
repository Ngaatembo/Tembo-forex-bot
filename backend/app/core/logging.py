"""
Structured logging configuration.

All engines (data, news, AI, strategy, risk) should log through this
module so that data-provider errors, missing data, AI failures, risk
blocks, and paper orders all end up in one consistent, queryable log
stream. This is required by the observability rules in docs/architecture.md.
"""

import logging
import sys
from datetime import datetime, timezone


class UTCFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = UTCFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
