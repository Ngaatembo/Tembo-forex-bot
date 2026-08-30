from app.technical_engine.regime import MarketRegime, RegimeInputs, classify_regime


def make_inputs(**overrides) -> RegimeInputs:
    defaults = dict(close=1.10, sma_50=1.09, sma_50_slope=0.0005, sma_distance_pct=0.002, atr_percent=0.001)
    defaults.update(overrides)
    return RegimeInputs(**defaults)


def test_unknown_when_any_input_is_none():
    assert classify_regime(make_inputs(sma_50=None)) == MarketRegime.UNKNOWN
    assert classify_regime(make_inputs(sma_50_slope=None)) == MarketRegime.UNKNOWN
    assert classify_regime(make_inputs(sma_distance_pct=None)) == MarketRegime.UNKNOWN
    assert classify_regime(make_inputs(atr_percent=None)) == MarketRegime.UNKNOWN
    assert classify_regime(make_inputs(close=None)) == MarketRegime.UNKNOWN


def test_high_volatility_takes_priority_over_trend():
    # This input would otherwise qualify as TRENDING_UP, but high ATR% wins.
    inputs = make_inputs(atr_percent=0.0020, close=1.10, sma_50=1.09, sma_50_slope=0.001, sma_distance_pct=0.005)
    assert classify_regime(inputs) == MarketRegime.HIGH_VOLATILITY


def test_low_volatility_classified_correctly():
    inputs = make_inputs(atr_percent=0.0002)
    assert classify_regime(inputs) == MarketRegime.LOW_VOLATILITY


def test_trending_up_requires_all_three_conditions():
    up = make_inputs(close=1.10, sma_50=1.09, sma_50_slope=0.001, sma_distance_pct=0.002, atr_percent=0.001)
    assert classify_regime(up) == MarketRegime.TRENDING_UP

    # price below SMA50 despite positive slope/separation -> not trending up
    not_up = make_inputs(close=1.08, sma_50=1.09, sma_50_slope=0.001, sma_distance_pct=0.002, atr_percent=0.001)
    assert classify_regime(not_up) != MarketRegime.TRENDING_UP


def test_trending_down_requires_all_three_conditions():
    down = make_inputs(close=1.08, sma_50=1.09, sma_50_slope=-0.001, sma_distance_pct=-0.002, atr_percent=0.001)
    assert classify_regime(down) == MarketRegime.TRENDING_DOWN


def test_insufficient_separation_falls_back_to_ranging():
    inputs = make_inputs(
        close=1.0901, sma_50=1.09, sma_50_slope=0.0001, sma_distance_pct=0.00005, atr_percent=0.001,
    )
    assert classify_regime(inputs) == MarketRegime.RANGING


def test_ranging_is_the_explicit_fallback():
    inputs = make_inputs(close=1.09, sma_50=1.09, sma_50_slope=0.0, sma_distance_pct=0.0, atr_percent=0.001)
    assert classify_regime(inputs) == MarketRegime.RANGING
