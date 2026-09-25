from datetime import datetime, timezone

from app.live_engine.candlesticks import PatternObservation
from app.signal_engine.decision_engine import evaluate_trade_decision
from app.technical_engine.models import FeatureSnapshot


def feature(**overrides):
    base = dict(
        timestamp=datetime.now(timezone.utc), close=1.1000,
        sma_10=1.1010, sma_50=1.0980, sma_50_slope=0.0001,
        sma_distance=0.003, sma_distance_pct=0.0027,
        rsi_14=60.0, atr_14=0.0010, atr_percent=0.0009,
        recent_high=1.1050, recent_low=1.0950, rolling_range=0.0100,
        distance_from_high=0.005, distance_from_low=0.005,
        regime="TRENDING_UP",
    )
    base.update(overrides)
    return FeatureSnapshot(**base)


def candle(name, direction):
    return PatternObservation(name, direction, "UP", True, False, "STRONG", (), "test")


def test_strong_aligned_factors_produce_buy_plan():
    result = evaluate_trade_decision(feature(), [candle("BULLISH_ENGULFING", "BULLISH")])
    assert result.decision == "BUY"
    assert result.direction == "BUY"
    assert result.stop_loss < result.entry < result.take_profit
    assert result.risk_reward >= 2.0
    assert result.confidence >= 65


def test_strong_downtrend_produces_sell_plan():
    result = evaluate_trade_decision(
        feature(
            close=1.0900, sma_10=1.0890, sma_50=1.0920, sma_50_slope=-0.0001,
            sma_distance=-0.003, sma_distance_pct=-0.0027,
            rsi_14=40.0, recent_high=1.0950, recent_low=1.0850,
            distance_from_high=0.005, distance_from_low=0.005,
            regime="TRENDING_DOWN",
        ),
        [candle("BEARISH_ENGULFING", "BEARISH")],
    )
    assert result.decision == "SELL"
    assert result.stop_loss > result.entry > result.take_profit


def test_high_volatility_fails_closed():
    result = evaluate_trade_decision(feature(regime="HIGH_VOLATILITY"), [])
    assert result.decision == "NO_TRADE"
    assert any("volatility" in reason.lower() for reason in result.rejection_reasons)


def test_missing_atr_fails_closed():
    result = evaluate_trade_decision(feature(atr_14=None, atr_percent=None), [])
    assert result.decision == "NO_TRADE"


def test_conflicting_candles_do_not_authorize_trade():
    patterns = [candle("BULLISH_ENGULFING", "BULLISH"), candle("BEARISH_ENGULFING", "BEARISH")]
    result = evaluate_trade_decision(feature(), patterns)
    assert result.decision == "NO_TRADE"


def test_weak_evidence_is_rejected():
    result = evaluate_trade_decision(feature(rsi_14=75.0), [])
    assert result.decision == "NO_TRADE"
    assert any("below" in reason.lower() for reason in result.rejection_reasons)


def test_macro_risk_restricts_even_strong_technical_evidence():
    result = evaluate_trade_decision(
        feature(),
        [candle("BULLISH_ENGULFING", "BULLISH")],
        macro_risk_level="HIGH",
    )
    assert result.decision == "NO_TRADE"
    assert any("macro risk" in reason.lower() for reason in result.rejection_reasons)
