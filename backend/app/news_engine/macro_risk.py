"""
Deterministic, rule-based MacroEventRisk. No AI, no invented
confidence scores. This layer may only provide context or RESTRICT
trading (force NO_TRADE) — it can never independently authorize one.
See decisions.py for exactly where this sits in the hierarchy.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.news_engine.models import (
    MACRO_RISK_HIGH, MACRO_RISK_LOW, MACRO_RISK_MEDIUM, MACRO_RISK_UNKNOWN, MacroEvent, MacroEventRisk,
)
from app.news_engine.relevance import CURRENCY_TO_INSTRUMENTS

DEFAULT_PROTECTION_WINDOW_HOURS = 2


def _relevant_currencies_for_instrument(instrument: str) -> tuple:
    return tuple(currency for currency, instruments in CURRENCY_TO_INSTRUMENTS.items() if instrument in instruments)


def compute_macro_event_risk(
    instrument: str,
    upcoming_events,
    now: Optional[datetime] = None,
    protection_window_hours: float = DEFAULT_PROTECTION_WINDOW_HOURS,
) -> MacroEventRisk:
    if upcoming_events is None:
        return MacroEventRisk(
            level=MACRO_RISK_UNKNOWN, reason="Economic calendar data is unavailable — risk cannot be assessed.",
            triggering_events=(),
        )

    now = now or datetime.now(timezone.utc)
    relevant_currencies = set(_relevant_currencies_for_instrument(instrument))
    window_end = now + timedelta(hours=protection_window_hours)

    relevant_events = [e for e in upcoming_events if e.currency in relevant_currencies]

    high_impact_soon = [e for e in relevant_events if e.importance == "HIGH" and now <= e.timestamp <= window_end]
    if high_impact_soon:
        names = ", ".join(e.event_name for e in high_impact_soon)
        return MacroEventRisk(
            level=MACRO_RISK_HIGH,
            reason=f"HIGH-importance event(s) affecting {instrument} within {protection_window_hours}h: {names}.",
            triggering_events=tuple(high_impact_soon),
        )

    medium_or_high_events = [
        e for e in relevant_events
        if e.importance in ("HIGH", "MEDIUM") and now <= e.timestamp <= now + timedelta(hours=protection_window_hours * 4)
    ]
    if medium_or_high_events:
        return MacroEventRisk(
            level=MACRO_RISK_MEDIUM,
            reason=f"{len(medium_or_high_events)} MEDIUM/HIGH-importance event(s) affecting {instrument} later today.",
            triggering_events=tuple(medium_or_high_events),
        )

    return MacroEventRisk(
        level=MACRO_RISK_LOW,
        reason=f"No HIGH/MEDIUM-importance events affecting {instrument} within the near-term window.",
        triggering_events=(),
    )
