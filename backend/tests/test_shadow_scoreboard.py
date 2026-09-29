import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data_engine.market_data import Candle
from app.research import shadow
from app.research.shadow import (
    SETUPS,
    SETUPS_BY_ID,
    WARMUP_CANDLES,
    candles_needed,
    completed_candles,
    floor_to_candle,
    replay,
    score,
    verdict,
)

START = datetime(2026, 3, 2, tzinfo=timezone.utc)


def make_candles(n: int, timeframe: str, instrument: str = "EUR/USD", seed: int = 7, price: float = 1.10) -> list[Candle]:
    rng = random.Random(seed)
    step = timedelta(minutes=shadow.TIMEFRAME_MINUTES[timeframe])
    out, drift = [], 0.0
    for i in range(n):
        if i % 150 == 0:
            drift = rng.choice([-1, 1]) * price * 0.0004
        o = price
        c = o + drift + rng.gauss(0, price * 0.0012)
        h = max(o, c) + abs(rng.gauss(0, price * 0.0006))
        low = min(o, c) - abs(rng.gauss(0, price * 0.0006))
        out.append(Candle(instrument, timeframe, START + i * step, o, h, low, c))
        price = c
    return out


def incremental(setup, candles, anchor, every):
    """What the live loop does: re-run from the stored anchor as candles arrive."""
    ledger = {}
    index = {c.timestamp: i for i, c in enumerate(candles)}
    open_trade = None
    for end in range(index[anchor] + 1, len(candles) + 1, every):
        start = max(0, index[anchor] - WARMUP_CANDLES)
        result = replay(setup, candles[start:end], anchor)
        for t in result.closed:
            ledger.setdefault(t["entry_at"], t)
        anchor, open_trade = result.new_anchor, result.open_trade
    return ledger, open_trade


@pytest.mark.parametrize("setup_id,timeframe,every", [
    ("eurusd_m15_sma_10_50", "m15", 1),
    ("eurusd_m15_sma_10_50", "m15", 7),
    ("usdjpy_h1_breakout_55", "h1", 5),
])
def test_incremental_tracking_matches_one_continuous_run(setup_id, timeframe, every):
    setup = SETUPS_BY_ID[setup_id]
    price = 150.0 if setup.instrument == "USD/JPY" else 1.10
    candles = make_candles(1400, timeframe, setup.instrument, price=price)
    anchor = candles[400].timestamp
    full = replay(setup, candles, anchor)
    assert len(full.closed) >= 5, "fixture should produce trades"

    ledger, open_trade = incremental(setup, candles, anchor, every)
    assert sorted(ledger) == [t["entry_at"] for t in full.closed]
    for t in full.closed:
        got = ledger[t["entry_at"]]
        assert got["exit_at"] == t["exit_at"] and got["direction"] == t["direction"]
        assert got["r_multiple"] == pytest.approx(t["r_multiple"], abs=1e-3)
    assert (open_trade is None) == (full.open_trade is None)


def test_only_signals_after_tracking_started_count():
    setup = SETUPS_BY_ID["eurusd_m15_sma_10_50"]
    candles = make_candles(900, "m15")
    anchor = candles[600].timestamp
    result = replay(setup, candles, anchor)
    assert all(t["signal_at"] >= anchor for t in result.closed)
    late = replay(setup, candles, candles[-1].timestamp + timedelta(minutes=15))
    assert late.closed == [] and late.open_trade is None


def test_trade_details_follow_the_research_exits():
    setup = SETUPS_BY_ID["eurusd_m15_sma_10_50"]
    result = replay(setup, make_candles(1400, "m15"), START)
    for t in result.closed:
        risk = abs(t["entry_price"] - t["stop_price"])
        reward = abs(t["target_price"] - t["entry_price"])
        assert reward == pytest.approx(2 * risk)  # ATR x4 target vs ATR x2 stop
        assert t["entry_at"] > t["signal_at"]  # entry on the next candle's open
        if t["exit_reason"] == "Stop loss":
            assert t["r_multiple"] < 0
        if t["exit_reason"] == "Take profit":
            assert t["r_multiple"] > 1.5


def test_completed_candles_drop_the_forming_candle():
    candles = make_candles(5, "h1")
    now = candles[-1].timestamp + timedelta(minutes=30)
    assert completed_candles(candles, "h1", now) == candles[:-1]
    assert floor_to_candle(datetime(2026, 9, 29, 7, 44, 10, tzinfo=timezone.utc), "m15") == datetime(2026, 9, 29, 7, 30, tzinfo=timezone.utc)
    assert floor_to_candle(datetime(2026, 9, 29, 7, 44, 10, tzinfo=timezone.utc), "h1") == datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc)
    assert candles_needed(START, "m15", START + timedelta(days=500)) == 5000


def test_score_in_r_and_dollars():
    s = score([2.0, -1.0, -1.0, 2.0, -1.0])
    assert s["trades"] == 5 and s["wins"] == 2 and s["win_rate"] == 0.4
    assert s["profit_factor"] == pytest.approx(4 / 3, abs=1e-3)
    assert s["net_r"] == 1.0 and s["net_usd_at_50_per_r"] == 50.0
    assert s["longest_losing_streak"] == 2
    assert score([1.0])["profit_factor"] is None  # no loss yet, no infinity in JSON
    assert score([])["win_rate"] is None


def test_pass_mark_is_applied_at_the_checkpoints():
    assert verdict([2.0] * 29)["state"] == "COLLECTING"
    good = [2.0, -1.0] * 15  # PF 2.0
    assert verdict(good)["state"] == "PASSED"
    bad = [1.0, -1.0, -1.0] * 10  # PF 0.5
    assert verdict(bad)["state"] == "FAILED"
    border = [1.05, -1.0] * 15  # PF 1.05
    assert verdict(border)["state"] == "EXTENDED"
    assert verdict(border + [1.1, -1.0] * 15)["state"] == "PASSED"  # 60-trade PF >= 1.05
    assert verdict(border + [0.5, -1.0] * 15)["state"] == "FAILED"
    # A later slump does not undo a pass that was already earned at 30.
    assert verdict(good + [-1.0] * 40)["state"] == "PASSED"


def test_results_payload_shape():
    from app.research.shadow_store import build_results

    now = datetime(2026, 9, 29, 8, tzinfo=timezone.utc)
    states = {
        "eurusd_m15_sma_10_50": SimpleNamespace(
            registered_at=now - timedelta(days=2), last_candle_at=now - timedelta(minutes=15), last_run_at=now,
            last_error=None, open_trade='{"direction": "BUY", "open_r": 0.4, "entry_price": 1.1}',
        )
    }
    trade = SimpleNamespace(
        setup_id="eurusd_m15_sma_10_50", instrument="EUR/USD", timeframe="m15", direction="SELL",
        signal_at=now - timedelta(hours=5), entry_at=now - timedelta(hours=4, minutes=45), entry_price=1.1,
        stop_price=1.102, target_price=1.096, exit_at=now - timedelta(hours=2), exit_price=1.096,
        exit_reason="Take profit", r_multiple=1.9,
    )
    payload = build_results(states, [trade], now)
    assert payload["paper_only"] is True
    assert [s["setup_id"] for s in payload["setups"]] == [s.setup_id for s in SETUPS]
    eur = next(s for s in payload["setups"] if s["setup_id"] == "eurusd_m15_sma_10_50")
    assert eur["score"]["trades"] == 1 and eur["open_trade"]["open_usd_at_50_per_r"] == 20.0
    assert eur["verdict"]["state"] == "COLLECTING"
    assert payload["trades"][0]["usd_at_50_per_r"] == 95.0
    jpy = next(s for s in payload["setups"] if s["setup_id"] == "usdjpy_h1_breakout_55")
    assert jpy["role"] == "forward_test" and jpy["tracking_since"] is None


def test_setups_are_the_registered_ones_and_paper_only():
    assert {s.setup_id for s in SETUPS} == {"usdjpy_h1_breakout_55", "eurusd_m15_sma_10_50", "xauusd_m15_sma_10_50"}
    assert [s.role for s in SETUPS].count("forward_test") == 1
    root = Path(__file__).resolve().parents[1] / "app"
    for path in (root / "research" / "shadow.py", root / "research" / "shadow_store.py", root / "api" / "routes" / "shadow.py"):
        source = path.read_text()
        for forbidden in ("DerivDemoClient", "buy_demo", "broker", "place_order", "execution"):
            assert forbidden not in source, f"{path.name} must stay paper-only ({forbidden})"


def test_update_runs_only_when_a_new_candle_has_closed():
    from app.research import shadow_store

    setup = SETUPS_BY_ID["eurusd_m15_sma_10_50"]
    shadow_store._next_try.clear()
    at = lambda h, m, s=0: datetime(2026, 9, 29, h, m, s, tzinfo=timezone.utc)  # noqa: E731
    assert shadow_store.last_expected_candle(setup, at(7, 44, 10)) == at(7, 15)
    assert shadow_store.last_expected_candle(setup, at(7, 45, 30)) == at(7, 30)
    state = SimpleNamespace(last_candle_at=at(7, 15))
    assert shadow_store.is_due(setup, None, at(7, 44))
    assert not shadow_store.is_due(setup, state, at(7, 44, 50))
    assert shadow_store.is_due(setup, state, at(7, 45, 30))
    shadow_store._next_try[setup.setup_id] = at(7, 50)  # backing off after an empty fetch
    assert not shadow_store.is_due(setup, state, at(7, 45, 30))
    shadow_store._next_try.clear()
