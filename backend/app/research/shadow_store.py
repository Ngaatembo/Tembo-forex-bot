"""Persistence and background loop for the shadow scoreboard (paper only)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.normalizer import normalize_candles
from app.database.models import ShadowSetupState, ShadowTrade
from app.database.session import AsyncSessionLocal
from app.research.shadow import (
    DOLLARS_PER_R,
    PASS_RULE,
    SETUPS,
    ShadowSetup,
    candle_step,
    candles_needed,
    completed_candles,
    floor_to_candle,
    replay,
    score,
    verdict,
)

logger = logging.getLogger(__name__)

SETTLE_SECONDS = 20  # give Deriv a moment to publish the closed candle
RETRY_AFTER_EMPTY = timedelta(minutes=5)  # weekends / market closed
RUN_TIMEOUT_SECONDS = 120  # one stuck request must never freeze the tracker
_next_try: dict[str, datetime] = {}
# In-memory health of the background loop, shown on the results endpoint.
tracker_status: dict = {"started_at": None, "heartbeat_at": None, "iterations": 0,
                        "running": None, "running_since": None, "last_loop_error": None}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value))


def last_expected_candle(setup: ShadowSetup, now: datetime) -> datetime:
    """Open time of the newest candle that should be closed by now."""
    return floor_to_candle(now - timedelta(seconds=SETTLE_SECONDS), setup.timeframe) - candle_step(setup.timeframe)


def is_due(setup: ShadowSetup, state: ShadowSetupState | None, now: datetime) -> bool:
    if now < _next_try.get(setup.setup_id, datetime.min.replace(tzinfo=timezone.utc)):
        return False
    if state is None or state.last_candle_at is None:
        return True
    return state.last_candle_at < last_expected_candle(setup, now)


async def run_setup(setup: ShadowSetup, now: datetime | None = None) -> dict:
    """Bring one setup's scoreboard up to date with every candle closed so far."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        state = await db.get(ShadowSetupState, setup.setup_id)
        if state is None:
            # Tracking starts with the candle that is forming right now.
            state = ShadowSetupState(
                setup_id=setup.setup_id,
                registered_at=now,
                anchor_at=floor_to_candle(now, setup.timeframe),
            )
            db.add(state)
            await db.commit()
            state = await db.get(ShadowSetupState, setup.setup_id)
        previous_last = state.last_candle_at
        try:
            provider = get_market_data_provider(settings.market_data_provider, setup.instrument)
            raw = await provider.get_candles(setup.instrument, setup.timeframe, limit=candles_needed(state.anchor_at, setup.timeframe, now))
            candles = completed_candles(normalize_candles(raw), setup.timeframe, now)
            if candles and candles[0].timestamp > state.anchor_at:
                logger.warning("Shadow %s: data starts after the anchor; results may miss a trade.", setup.setup_id)
            result = replay(setup, candles, state.anchor_at)
            for trade in result.closed:
                await db.execute(
                    insert(ShadowTrade).values(**trade).on_conflict_do_nothing(constraint="uq_shadow_trade_identity")
                )
            state.anchor_at = result.new_anchor
            state.last_candle_at = result.last_candle_at or state.last_candle_at
            state.open_trade = json.dumps(result.open_trade, default=_json_default) if result.open_trade else None
            state.last_error = None
            state.last_run_at = now
            await db.commit()
            new_candle = result.last_candle_at is not None and result.last_candle_at != previous_last
            _next_try[setup.setup_id] = now + (timedelta(seconds=30) if new_candle else RETRY_AFTER_EMPTY)
            return {"setup_id": setup.setup_id, "closed": len(result.closed), "open": result.open_trade is not None}
        except Exception as exc:
            await db.rollback()
            state = await db.get(ShadowSetupState, setup.setup_id)
            state.last_error = f"{type(exc).__name__}: {exc}"[:500]
            state.last_run_at = now
            await db.commit()
            _next_try[setup.setup_id] = now + RETRY_AFTER_EMPTY
            raise


def _note_error(where: str, exc: Exception) -> None:
    tracker_status["last_loop_error"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "where": where,
        "error": f"{type(exc).__name__}: {exc}"[:500],
    }


async def shadow_loop() -> None:
    logger.info("Shadow scoreboard enabled for %s (paper only).", ", ".join(s.setup_id for s in SETUPS))
    tracker_status["started_at"] = datetime.now(timezone.utc).isoformat()
    while True:
        try:
            now = datetime.now(timezone.utc)
            tracker_status["heartbeat_at"] = now.isoformat()
            tracker_status["iterations"] += 1
            async with AsyncSessionLocal() as db:
                states = {s.setup_id: s for s in (await db.execute(select(ShadowSetupState))).scalars().all()}
            for setup in SETUPS:
                if is_due(setup, states.get(setup.setup_id), now):
                    tracker_status["running"], tracker_status["running_since"] = setup.setup_id, datetime.now(timezone.utc).isoformat()
                    try:
                        await asyncio.wait_for(run_setup(setup, now), timeout=RUN_TIMEOUT_SECONDS)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # includes timeouts
                        _next_try[setup.setup_id] = datetime.now(timezone.utc) + timedelta(minutes=1)
                        _note_error(setup.setup_id, exc)
                        logger.exception("Shadow scoreboard update failed for %s; will retry.", setup.setup_id)
                    finally:
                        tracker_status["running"], tracker_status["running_since"] = None, None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _note_error("loop", exc)
            logger.exception("Shadow scoreboard loop iteration failed; will retry.")
        await asyncio.sleep(30)


def _trade_row(t: ShadowTrade) -> dict:
    return {
        "setup_id": t.setup_id,
        "instrument": t.instrument,
        "timeframe": t.timeframe,
        "direction": t.direction,
        "signal_at": _iso(t.signal_at),
        "entry_at": _iso(t.entry_at),
        "entry_price": t.entry_price,
        "stop_price": t.stop_price,
        "target_price": t.target_price,
        "exit_at": _iso(t.exit_at),
        "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "r_multiple": t.r_multiple,
        "usd_at_50_per_r": round(t.r_multiple * DOLLARS_PER_R, 2),
    }


def build_results(states: dict[str, ShadowSetupState], trades: list[ShadowTrade], now: datetime) -> dict:
    by_setup: dict[str, list[ShadowTrade]] = {s.setup_id: [] for s in SETUPS}
    for t in trades:
        by_setup.setdefault(t.setup_id, []).append(t)
    setups = []
    for setup in SETUPS:
        state = states.get(setup.setup_id)
        closed = sorted(by_setup.get(setup.setup_id, []), key=lambda t: (t.exit_at, t.entry_at))
        rs = [t.r_multiple for t in closed]
        open_trade = json.loads(state.open_trade) if state and state.open_trade else None
        if open_trade and open_trade.get("open_r") is not None:
            open_trade["open_usd_at_50_per_r"] = round(open_trade["open_r"] * DOLLARS_PER_R, 2)
        setups.append({
            "setup_id": setup.setup_id,
            "label": setup.label,
            "instrument": setup.instrument,
            "timeframe": setup.timeframe,
            "role": setup.role,
            "why": setup.why,
            "baseline": setup.baseline,
            "tracking_since": _iso(state.registered_at) if state else None,
            "last_candle_at": _iso(state.last_candle_at) if state else None,
            "last_run_at": _iso(state.last_run_at) if state else None,
            "last_error": state.last_error if state else None,
            "score": score(rs),
            "verdict": verdict(rs),
            "open_trade": open_trade,
        })
    recent = sorted(trades, key=lambda t: t.exit_at, reverse=True)[:100]
    all_rs = [t.r_multiple for t in sorted(trades, key=lambda t: t.exit_at)]
    return {
        "generated_at": now.isoformat(),
        "paper_only": True,
        "dollars_per_r": DOLLARS_PER_R,
        "pass_rule": PASS_RULE,
        "combined": score(all_rs),
        "tracker": dict(tracker_status),
        "setups": setups,
        "trades": [_trade_row(t) for t in recent],
    }


async def load_results() -> dict:
    async with AsyncSessionLocal() as db:
        states = {s.setup_id: s for s in (await db.execute(select(ShadowSetupState))).scalars().all()}
        trades = list((await db.execute(select(ShadowTrade))).scalars().all())
    return build_results(states, trades, datetime.now(timezone.utc))
