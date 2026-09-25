from types import SimpleNamespace

from app.live_engine.candlesticks import detect_candlestick_patterns


def candle(o: float, h: float, l: float, c: float):
    return SimpleNamespace(open=o, high=h, low=l, close=c)


def downtrend(count: int = 12):
    price = 1.2000
    rows = []
    for _ in range(count):
        close = price - 0.0020
        rows.append(candle(price, price + 0.0001, close - 0.0001, close))
        price = close
    return rows


def uptrend(count: int = 12):
    price = 1.1000
    rows = []
    for _ in range(count):
        close = price + 0.0020
        rows.append(candle(price, close + 0.0001, price - 0.0001, close))
        price = close
    return rows


def test_hammer_requires_downtrend_context_and_confirmation():
    candles = downtrend()
    price = candles[-1].close
    candles.append(candle(price, price + 0.00005, price - 0.0040, price + 0.0003))
    patterns = detect_candlestick_patterns(candles)
    hammer = next(p for p in patterns if p.name == "HAMMER")
    assert hammer.direction == "BULLISH"
    assert hammer.confirmed is False

    confirmation_price = candles[-1].close
    candles.append(candle(
        confirmation_price,
        confirmation_price + 0.0010,
        confirmation_price + 0.0001,
        confirmation_price + 0.0007,
    ))
    confirmed = detect_candlestick_patterns(candles)
    confirmed_hammer = next(p for p in confirmed if p.name == "HAMMER" and p.confirmed)
    assert confirmed_hammer.confirmation_required is True


def test_bullish_engulfing_requires_downtrend_and_engulfs_body():
    candles = downtrend()
    p = candles[-1].close
    candles.extend([
        candle(p, p + 0.0001, p - 0.0010, p - 0.0007),
        candle(p - 0.0007, p + 0.0015, p - 0.0008, p + 0.0010),
    ])
    patterns = detect_candlestick_patterns(candles)
    engulf = next(p for p in patterns if p.name == "BULLISH_ENGULFING")
    assert engulf.confirmed is True
    assert "current_body_engulfs_prior_body" in engulf.evidence


def test_bearish_engulfing_requires_uptrend_and_engulfs_body():
    candles = uptrend()
    p = candles[-1].close
    candles.extend([
        candle(p, p + 0.0010, p - 0.0001, p + 0.0007),
        candle(p + 0.0007, p + 0.0008, p - 0.0015, p - 0.0010),
    ])
    patterns = detect_candlestick_patterns(candles)
    engulf = next(p for p in patterns if p.name == "BEARISH_ENGULFING")
    assert engulf.confirmed is True


def test_pattern_detector_never_looks_ahead():
    candles = downtrend()
    p = candles[-1].close
    candles.append(candle(p, p + 0.00005, p - 0.0040, p + 0.0003))
    patterns = detect_candlestick_patterns(candles)
    hammer = next(p for p in patterns if p.name == "HAMMER")
    assert hammer.confirmation_required is True
    assert hammer.confirmed is False

    p = candles[-1].close
    candles.append(candle(p, p + 0.0010, p + 0.0001, p + 0.0007))
    confirmed = detect_candlestick_patterns(candles)
    assert any(p.name == "HAMMER" and p.confirmed for p in confirmed)


def test_research_cost_helper_is_monotonic():
    from scripts.run_candlestick_book_research import net_return
    low = net_return(0.0010, 1.1000, 0.5)
    high = net_return(0.0010, 1.1000, 2.0)
    assert low > high


def test_research_wilson_interval_contains_observed_rate():
    from scripts.run_candlestick_book_research import wilson_interval
    low, high = wilson_interval(55, 100)
    assert low < 0.55 < high



def test_analysis_includes_candlestick_evidence_without_trade_signal():
    from datetime import datetime, timedelta, timezone
    from app.data_engine.market_data import Candle
    from app.live_engine.analysis import analyze_candles

    candles = []
    price = 1.1000
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(60):
        close = price + 0.0005
        candles.append(Candle("EUR/USD", "h1", start + timedelta(hours=i), price, close + 0.0001, price - 0.0001, close))
        price = close

    result = analyze_candles(candles)
    assert "candlestick_patterns" in result
    assert isinstance(result["candlestick_patterns"], list)
    assert "decision" not in result
