"""
Phone alerts for Tembo signals.

Schedule (H1, UTC-aligned like the Deriv candles):
- HH:55  heads-up: re-run the selected researched strategy on the candle that
         is still forming, using the live price as its provisional close. If it
         would fire right now, warn that a signal may confirm at the close.
- HH:01  confirmation: run the normal /live/decision chain on the candle that
         just closed. Send the confirmed BUY/SELL with entry/SL/TP, or tell the
         user that the heads-up did not confirm.

Alerts only report. They never open, change or close a position, and a
heads-up is never a trade instruction: only the post-close decision is.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import get_settings
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles
from app.research.forward_test import forward_test_config_ids, is_forward_test
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig

logger = logging.getLogger(__name__)

ALERT_INSTRUMENTS = ("EUR/USD", "GBP/USD", "XAU/USD")
TIMEFRAME = "h1"
HEADS_UP_MINUTE = 55
CONFIRM_MINUTE = 1
CODES = {"EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "XAU/USD": "XAUUSD", "USD/JPY": "USDJPY"}

# In-memory state: which candles already produced which alert, plus a short
# history the dashboard can show. A restart at worst repeats one alert.
_heads_up_sent: dict[tuple[str, str], str] = {}
_confirm_sent: set[tuple[str, str]] = set()
_done_slots: set[str] = set()
recent_alerts: deque = deque(maxlen=20)


def _configs() -> list[ValidatedStrategyConfig]:
    path = Path(__file__).resolve().parents[3] / "research" / "results" / "validated_strategy_configs.json"
    if not path.exists():
        return []
    try:
        return [ValidatedStrategyConfig.from_dict(item) for item in json.loads(path.read_text())]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def _digits(instrument: str) -> int:
    return 2 if instrument.startswith("XAU") else 3 if "JPY" in instrument else 5


def _fmt(value: float | None, instrument: str) -> str:
    return "—" if value is None else f"{value:,.{_digits(instrument)}f}"


def due_jobs(now: datetime) -> list[tuple[str, str]]:
    """Which jobs should run at `now` (UTC). Returns (job, slot_key) pairs not yet done."""
    jobs = []
    if now.minute == HEADS_UP_MINUTE:
        close_at = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat()
        jobs.append(("heads_up", f"heads_up:{close_at}"))
    if now.minute in (CONFIRM_MINUTE, CONFIRM_MINUTE + 1):
        closed_at = now.replace(minute=0, second=0, microsecond=0).isoformat()
        jobs.append(("confirm", f"confirm:{closed_at}"))
    return [(job, slot) for job, slot in jobs if slot not in _done_slots]


def heads_up_message(instrument: str, direction: str, price: float, close_at: datetime, forward_test: bool) -> dict:
    code = CODES.get(instrument, instrument)
    return {
        "title": f"Heads-up: {code} may signal {direction}",
        "body": (
            f"{code} is breaking out at {_fmt(price, instrument)} with about 5 minutes left in the H1 candle. "
            "Tembo confirms when the candle closes on the hour"
            + (" (forward test, demo only)." if forward_test else ".")
        ),
        "tag": f"tembo-{code}-{close_at:%Y%m%d%H}",
        "url": f"/#/live/{instrument.replace('/', '%2F')}",
        "kind": "heads_up",
    }


def signal_message(instrument: str, decision: dict) -> dict:
    code = CODES.get(instrument, instrument)
    plan = decision.get("trade_plan") or {}
    direction = decision.get("decision")
    forward = (decision.get("forward_test") or {}).get("active")
    return {
        "title": f"Tembo signal: {direction} {code}" + (" (forward test)" if forward else ""),
        "body": (
            f"Entry {_fmt(plan.get('entry'), instrument)} · SL {_fmt(plan.get('stop_loss'), instrument)} · "
            f"TP {_fmt(plan.get('take_profit'), instrument)}. Open the dashboard to place the demo trade."
        ),
        "tag": f"tembo-{code}-signal",
        "url": f"/#/live/{instrument.replace('/', '%2F')}",
        "kind": "signal",
    }


def no_confirm_message(instrument: str, decision: dict) -> dict:
    code = CODES.get(instrument, instrument)
    reason = (decision.get("trade_plan") or {}).get("reason") or decision.get("message") or "The setup did not hold at the close."
    return {
        "title": f"No signal on {code} after all",
        "body": f"The heads-up did not confirm at the candle close. {reason}",
        "tag": f"tembo-{code}-signal",
        "url": f"/#/live/{instrument.replace('/', '%2F')}",
        "kind": "no_confirm",
    }


async def _deliver(payload: dict) -> None:
    from app.alerts.store import send_alert

    result = await send_alert(payload)
    recent_alerts.appendleft({"at": datetime.now(timezone.utc).isoformat(), **payload, "delivery": result})
    logger.info("Alert %r delivered: %s", payload.get("title"), result)


async def heads_up_check(now: datetime) -> list[dict]:
    """Would the selected strategy fire if the forming candle closed at the live price?"""
    settings = get_settings()
    configs = _configs()
    allowed = forward_test_config_ids()
    close_at = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    sent = []

    from app.news_engine.context import get_upcoming_macro_events
    from app.news_engine.macro_risk import compute_macro_event_risk
    from app.strategy_engine.service import evaluate_live_strategy
    from app.technical_engine.features import calculate_feature_snapshots

    for instrument in ALERT_INSTRUMENTS:
        key = (instrument, close_at.isoformat())
        if key in _heads_up_sent:
            continue
        try:
            provider = get_market_data_provider(settings.market_data_provider, instrument)
            candles = normalize_candles(await provider.get_candles(instrument, TIMEFRAME, limit=200))
            if not candles or candles[-1].timestamp + timedelta(hours=1) <= now:
                continue  # no forming candle (e.g. market closed)
            completed, forming = candles[:-1], candles[-1]
            if len(completed) < 50 or not validate_candles(completed, timeframe=TIMEFRAME).is_clean:
                continue
            price = float(await provider.get_current_price(instrument))
            provisional = replace(forming, close=price, high=max(forming.high, price), low=min(forming.low, price))
            series = completed + [provisional]

            snapshots = calculate_feature_snapshots(series)
            if not snapshots:
                continue
            selection = select_strategy(instrument, TIMEFRAME, configs, current_regime=snapshots[-1].regime)
            forward = is_forward_test(selection.status, selection.selected_config_id, allowed)
            if selection.status != "TRADEABLE" and not forward:
                continue
            config = next((c for c in configs if c.config_id == selection.selected_config_id), None)
            if config is None:
                continue
            result = evaluate_live_strategy(series, instrument, config, atr=snapshots[-1].atr_14)
            if not result.triggered or result.direction not in {"BUY", "SELL"}:
                continue

            macro = compute_macro_event_risk(instrument, await get_upcoming_macro_events(lookahead_hours=2, lookback_hours=0))
            if macro.level in {"HIGH", "MEDIUM", "UNKNOWN"}:
                continue  # Tembo would block it at the close anyway

            payload = heads_up_message(instrument, result.direction, price, close_at, forward)
            await _deliver(payload)
            _heads_up_sent[key] = result.direction
            sent.append(payload)
        except Exception:
            logger.exception("Heads-up check failed for %s", instrument)
    return sent


async def confirm_check(now: datetime) -> list[dict]:
    """After the close: send the confirmed signal, or say a heads-up did not confirm."""
    from app.api.routes.live import live_decision

    closed_at = now.replace(minute=0, second=0, microsecond=0)
    sent = []
    for instrument in ALERT_INSTRUMENTS:
        try:
            decision = await live_decision(instrument=instrument, timeframe=TIMEFRAME)
            candle = (decision.get("data_quality") or {}).get("last_candle") or closed_at.isoformat()
            key = (instrument, candle)
            if key in _confirm_sent:
                continue
            eligible = (decision.get("paper_eligibility") or {}).get("eligible")
            if decision.get("decision") in {"BUY", "SELL"} and eligible:
                payload = signal_message(instrument, decision)
            elif (instrument, closed_at.isoformat()) in _heads_up_sent:
                payload = no_confirm_message(instrument, decision)
            else:
                continue
            await _deliver(payload)
            _confirm_sent.add(key)
            sent.append(payload)
        except Exception:
            logger.exception("Signal confirmation check failed for %s", instrument)
    return sent


async def alert_loop() -> None:
    """Wake twice a minute; run each scheduled job once per slot."""
    logger.info("Phone alerts enabled: heads-up at :%02d, confirmation at :%02d (UTC hours).", HEADS_UP_MINUTE, CONFIRM_MINUTE)
    while True:
        try:
            now = datetime.now(timezone.utc)
            for job, slot in due_jobs(now):
                _done_slots.add(slot)
                if job == "heads_up":
                    await heads_up_check(now)
                else:
                    await confirm_check(now)
            if len(_done_slots) > 200:
                _done_slots.clear()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alert loop iteration failed; it will retry.")
        await asyncio.sleep(30)


def next_schedule(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    top = now.replace(minute=0, second=0, microsecond=0)
    heads_up = top + timedelta(minutes=HEADS_UP_MINUTE)
    if heads_up <= now:
        heads_up += timedelta(hours=1)
    confirm = top + timedelta(minutes=CONFIRM_MINUTE)
    if confirm <= now:
        confirm += timedelta(hours=1)
    return {"next_heads_up_check": heads_up.isoformat(), "next_confirmation_check": confirm.isoformat()}
