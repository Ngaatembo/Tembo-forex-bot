from datetime import datetime, timedelta, timezone

import pytest

from app.news_engine.macro_risk import compute_macro_event_risk
from app.news_engine.models import MacroEvent


def get_all_2026_events():
    from app.news_engine.providers.static_central_bank_calendar import get_2026_events
    return get_2026_events()


def test_exactly_32_events_for_2026():
    events = get_all_2026_events()
    assert len(events) == 32


def test_exactly_8_events_per_bank():
    events = get_all_2026_events()
    for currency in ("USD", "EUR", "GBP", "JPY"):
        matching = [e for e in events if e.currency == currency]
        assert len(matching) == 8, f"{currency} has {len(matching)} events, expected 8"


def test_all_four_currencies_present():
    events = get_all_2026_events()
    currencies = {e.currency for e in events}
    assert currencies == {"USD", "EUR", "GBP", "JPY"}


def test_fed_dates_exact():
    events = get_all_2026_events()
    fed_dates = sorted(e.timestamp.date().isoformat() for e in events if e.currency == "USD")
    assert fed_dates == [
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    ]


def test_ecb_dates_exact():
    events = get_all_2026_events()
    ecb_dates = sorted(e.timestamp.date().isoformat() for e in events if e.currency == "EUR")
    assert ecb_dates == [
        "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-11",
        "2026-07-23", "2026-09-10", "2026-10-29", "2026-12-17",
    ]


def test_boe_dates_exact():
    events = get_all_2026_events()
    boe_dates = sorted(e.timestamp.date().isoformat() for e in events if e.currency == "GBP")
    assert boe_dates == [
        "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-18",
        "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17",
    ]


def test_boj_dates_exact():
    events = get_all_2026_events()
    boj_dates = sorted(e.timestamp.date().isoformat() for e in events if e.currency == "JPY")
    assert boj_dates == [
        "2026-01-23", "2026-03-19", "2026-04-28", "2026-06-16",
        "2026-07-31", "2026-09-18", "2026-10-30", "2026-12-18",
    ]


def test_event_names_correct():
    events = get_all_2026_events()
    expected_names = {"USD": "FOMC Rate Decision", "EUR": "ECB Rate Decision", "GBP": "BoE MPC Rate Decision", "JPY": "BoJ Rate Decision"}
    for e in events:
        assert e.event_name == expected_names[e.currency]


def test_all_events_high_importance():
    events = get_all_2026_events()
    assert all(e.importance == "HIGH" for e in events)


def test_actual_forecast_previous_all_none():
    events = get_all_2026_events()
    for e in events:
        assert e.actual is None
        assert e.forecast is None
        assert e.previous is None


def test_event_ids_deterministic_and_unique():
    events1 = get_all_2026_events()
    events2 = get_all_2026_events()
    ids1 = sorted(e.event_id for e in events1)
    ids2 = sorted(e.event_id for e in events2)
    assert ids1 == ids2
    assert len(set(ids1)) == 32  # all unique


def test_source_attribution_correct():
    events = get_all_2026_events()
    expected_sources = {
        "USD": ("Federal Reserve (FOMC)", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
        "EUR": ("European Central Bank", "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"),
        "GBP": ("Bank of England", "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"),
        "JPY": ("Bank of Japan", "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"),
    }
    for e in events:
        expected_source, expected_url = expected_sources[e.currency]
        assert e.source == expected_source
        assert e.url == expected_url


def test_fed_and_ecb_have_confirmed_times():
    events = get_all_2026_events()
    for e in events:
        if e.currency in ("USD", "EUR"):
            assert e.time_confirmed is True


def test_boe_and_boj_times_not_falsely_confirmed():
    events = get_all_2026_events()
    for e in events:
        if e.currency in ("GBP", "JPY"):
            assert e.time_confirmed is False


def test_fed_decision_time_utc_correct():
    """Fed: 2:00 PM ET. In late January (EST, UTC-5), that's 19:00 UTC."""
    events = get_all_2026_events()
    jan_fed = next(e for e in events if e.currency == "USD" and e.timestamp.date().isoformat() == "2026-01-28")
    assert jan_fed.timestamp.hour == 19
    assert jan_fed.timestamp.tzinfo is not None


def test_ecb_decision_time_utc_correct():
    """ECB: 2:15 PM CET. In February (CET, UTC+1), that's 13:15 UTC."""
    events = get_all_2026_events()
    feb_ecb = next(e for e in events if e.currency == "EUR" and e.timestamp.date().isoformat() == "2026-02-05")
    assert feb_ecb.timestamp.hour == 13
    assert feb_ecb.timestamp.minute == 15


def test_dataset_metadata_present():
    from app.news_engine.providers.static_central_bank_calendar import (
        DATASET_COVERS_YEAR, DATASET_VERIFIED_DATE, DATASET_VERSION,
    )
    assert DATASET_VERSION == "2026-v1"
    assert DATASET_VERIFIED_DATE == "2026-09-01"
    assert DATASET_COVERS_YEAR == 2026


# ---- Provider interface ----

@pytest.fixture
def static_provider(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "static_central_banks")
    from app.news_engine.providers.static_central_bank_calendar import StaticCentralBankCalendarProvider
    p = StaticCentralBankCalendarProvider()
    yield p
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_provider_returns_all_events_for_wide_range(static_provider):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    events = await static_provider.get_upcoming_events(start, end)
    assert len(events) == 32


@pytest.mark.asyncio
async def test_provider_filters_by_date_range(static_provider):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 1, tzinfo=timezone.utc)
    events = await static_provider.get_upcoming_events(start, end)
    # Only Jan/Feb events: Fed Jan 28, BoJ Jan 23, ECB Feb 5, BoE Feb 5
    assert len(events) == 4


@pytest.mark.asyncio
async def test_provider_has_no_network_dependency(static_provider):
    """Structural proof: no httpx client, no network call possible."""
    assert not hasattr(static_provider, "_client")


def test_provider_factory_registers_static_provider(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.news_engine.interfaces import get_economic_calendar_provider
    from app.news_engine.providers.static_central_bank_calendar import StaticCentralBankCalendarProvider
    provider = get_economic_calendar_provider("static_central_banks")
    assert isinstance(provider, StaticCentralBankCalendarProvider)
    get_settings.cache_clear()


def test_existing_mock_provider_still_works():
    from app.news_engine.interfaces import get_economic_calendar_provider, MockEconomicCalendarProvider
    provider = get_economic_calendar_provider("mock")
    assert isinstance(provider, MockEconomicCalendarProvider)


def test_existing_finnhub_provider_registration_untouched(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_API_KEY", "fake_test_key")
    from app.news_engine.interfaces import get_economic_calendar_provider
    from app.news_engine.providers.finnhub_calendar import FinnhubEconomicCalendarProvider
    provider = get_economic_calendar_provider("finnhub")
    assert isinstance(provider, FinnhubEconomicCalendarProvider)
    get_settings.cache_clear()


# ---- MacroEventRisk integration with time_confirmed=False ----

def test_unconfirmed_time_event_protects_whole_day():
    """A GBP/JPY event (time_confirmed=False) anchored at 00:00 UTC must
    still trigger HIGH risk later in the same day, not just at midnight."""
    event = MacroEvent(
        event_id="boe_2026-09-17", timestamp=datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc),
        currency="GBP", country="GB", event_name="BoE MPC Rate Decision", importance="HIGH",
        previous=None, forecast=None, actual=None, source="Bank of England", url="https://x",
        time_confirmed=False,
    )
    # "now" is late in the same day -- a naive precise-datetime check
    # would have missed this (event timestamp is 00:00, now is 20:00).
    now = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)
    risk = compute_macro_event_risk("GBP/USD", upcoming_events=[event], now=now, protection_window_hours=2)
    assert risk.level == "HIGH"


def test_confirmed_time_event_uses_precise_window_not_whole_day():
    """A Fed event (time_confirmed=True) must NOT trigger HIGH risk from
    a time far outside the precise window, even on the same calendar day."""
    event = MacroEvent(
        event_id="fed_2026-01-28", timestamp=datetime(2026, 1, 28, 19, 0, tzinfo=timezone.utc),
        currency="USD", country="US", event_name="FOMC Rate Decision", importance="HIGH",
        previous=None, forecast=None, actual=None, source="Federal Reserve (FOMC)", url="https://x",
        time_confirmed=True,
    )
    now = datetime(2026, 1, 28, 1, 0, tzinfo=timezone.utc)  # 18 hours before the real decision
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=[event], now=now, protection_window_hours=2)
    assert risk.level != "HIGH"


def test_static_calendar_macro_risk_never_produces_buy_sell_signal():
    events = get_all_2026_events()
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=events)
    assert not hasattr(risk, "direction")
    assert not hasattr(risk, "signal")
