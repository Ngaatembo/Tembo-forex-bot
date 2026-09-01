"""
Static Official Central Bank Calendar — Phase 1.

This is explicitly NOT a live feed. It is a manually verified,
attributed record of officially published central-bank rate-decision
dates, transcribed directly from each bank's own official page on
2026-09-01 (see DATASET_VERIFIED_DATE). It is refreshed as a periodic
maintenance task (a new versioned dataset per year), never fetched at
runtime, and never scrapes any page. GET /calendar reports this
provider's status as "STATIC_OFFICIAL", never "LIVE" — see
app/api/routes/news.py.

Every date below was independently verified against the bank's own
official page before being written here — see each bank's
source/source_url. No date was estimated, extrapolated, or sourced
from a third-party calendar.

ANNOUNCEMENT TIME HANDLING:
- Fed (2:00 PM ET) and ECB (2:15 PM CET) have officially confirmed
  decision times on their own source pages -- converted to UTC here
  using zoneinfo (correctly DST-aware for the specific date, not a
  hand-computed fixed offset), with time_confirmed=True.
- BoE and Bank of Japan's official pages do NOT state an exact
  rate-decision announcement time (only publish minutes/summary
  release times, not the decision itself) -- their timestamp is a
  neutral 00:00:00 UTC anchor on the correct date, with
  time_confirmed=False. See models.py and macro_risk.py for how this
  flag changes downstream window-matching behavior (whole-day
  coverage instead of a precise-time match).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.news_engine.interfaces import EconomicCalendarProvider
from app.news_engine.models import MacroEvent

DATASET_VERSION = "2026-v1"
DATASET_VERIFIED_DATE = "2026-09-01"
DATASET_COVERS_YEAR = 2026

_ET = ZoneInfo("America/New_York")
_CET = ZoneInfo("Europe/Berlin")

_FED_SOURCE = ("Federal Reserve (FOMC)", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
_ECB_SOURCE = ("European Central Bank", "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html")
_BOE_SOURCE = ("Bank of England", "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates")
_BOJ_SOURCE = ("Bank of Japan", "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm")

_FED_DATES_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]
_ECB_DATES_2026 = ["2026-02-05", "2026-03-19", "2026-04-30", "2026-06-11", "2026-07-23", "2026-09-10", "2026-10-29", "2026-12-17"]
_BOE_DATES_2026 = ["2026-02-05", "2026-03-19", "2026-04-30", "2026-06-18", "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17"]
_BOJ_DATES_2026 = ["2026-01-23", "2026-03-19", "2026-04-28", "2026-06-16", "2026-07-31", "2026-09-18", "2026-10-30", "2026-12-18"]


def _fed_event(date_str: str) -> MacroEvent:
    local_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=14, minute=0, tzinfo=_ET)
    source, url = _FED_SOURCE
    return MacroEvent(
        event_id=f"fed_{date_str}", timestamp=local_dt.astimezone(timezone.utc),
        currency="USD", country="US", event_name="FOMC Rate Decision", importance="HIGH",
        previous=None, forecast=None, actual=None, source=source, url=url, time_confirmed=True,
    )


def _ecb_event(date_str: str) -> MacroEvent:
    local_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=14, minute=15, tzinfo=_CET)
    source, url = _ECB_SOURCE
    return MacroEvent(
        event_id=f"ecb_{date_str}", timestamp=local_dt.astimezone(timezone.utc),
        currency="EUR", country="EU", event_name="ECB Rate Decision", importance="HIGH",
        previous=None, forecast=None, actual=None, source=source, url=url, time_confirmed=True,
    )


def _boe_event(date_str: str) -> MacroEvent:
    utc_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    source, url = _BOE_SOURCE
    return MacroEvent(
        event_id=f"boe_{date_str}", timestamp=utc_dt,
        currency="GBP", country="GB", event_name="BoE MPC Rate Decision", importance="HIGH",
        previous=None, forecast=None, actual=None, source=source, url=url, time_confirmed=False,
    )


def _boj_event(date_str: str) -> MacroEvent:
    utc_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    source, url = _BOJ_SOURCE
    return MacroEvent(
        event_id=f"boj_{date_str}", timestamp=utc_dt,
        currency="JPY", country="JP", event_name="BoJ Rate Decision", importance="HIGH",
        previous=None, forecast=None, actual=None, source=source, url=url, time_confirmed=False,
    )


def get_2026_events() -> list[MacroEvent]:
    events = []
    events.extend(_fed_event(d) for d in _FED_DATES_2026)
    events.extend(_ecb_event(d) for d in _ECB_DATES_2026)
    events.extend(_boe_event(d) for d in _BOE_DATES_2026)
    events.extend(_boj_event(d) for d in _BOJ_DATES_2026)
    return events


class StaticCentralBankCalendarProvider(EconomicCalendarProvider):
    """No network dependency at all -- get_upcoming_events() only
    filters an in-memory, hand-verified list. Selected via
    ECONOMIC_CALENDAR_PROVIDER=static_central_banks."""

    async def get_upcoming_events(self, start: datetime, end: datetime) -> list[MacroEvent]:
        all_events = get_2026_events()  # future years: add get_2027_events() etc. and concatenate here
        return [e for e in all_events if start <= e.timestamp <= end]
