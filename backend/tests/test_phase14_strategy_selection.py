import pytest

from app.research.hypothesis import HypothesisType
from app.research.instrument_adapter import (
    build_instrument_timeframe_info, compute_notionally_comparable_position_size,
)
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.data_engine.market_data import Candle
from datetime import datetime, timedelta, timezone

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def make_config(**overrides) -> ValidatedStrategyConfig:
    defaults = dict(
        config_id="vsc_test1", candidate_id="cand_test1", instrument="XAU/USD", timeframe="h1",
        strategy_family=HypothesisType.BREAKOUT, parameters={"lookback": 40},
        exit_config_summary={"atr_stop_multiple": 2.0}, cost_assumptions={"spread": 0.0001},
        evidence_period_start="2012-01-01T00:00:00+00:00", evidence_period_end="2022-01-01T00:00:00+00:00",
        gate_status="PROMISING", verdict="PROMISING", statistical_level="WEAK",
        regime_evidence={"HIGH_VOLATILITY": 158},
    )
    defaults.update(overrides)
    return ValidatedStrategyConfig(**defaults)


def test_valid_config_constructs():
    c = make_config()
    assert c.gate_status == "PROMISING"


def test_invalid_gate_status_rejected():
    with pytest.raises(ValueError):
        make_config(gate_status="NOT_A_REAL_STATUS")


def test_invalid_statistical_level_rejected():
    with pytest.raises(ValueError):
        make_config(statistical_level="SUPER_STRONG")


def test_missing_instrument_or_timeframe_rejected():
    with pytest.raises(ValueError):
        make_config(instrument="")


def test_config_serialization_round_trip():
    c = make_config()
    restored = ValidatedStrategyConfig.from_dict(c.to_dict())
    assert restored == c


def test_config_is_immutable():
    import dataclasses
    c = make_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.gate_status = "CLOSED"


def _candles(prices):
    return [
        Candle(symbol="X", timeframe="h1", timestamp=BASE + timedelta(hours=i),
               open=p, high=p + 0.01, low=p - 0.01, close=p, volume=100)
        for i, p in enumerate(prices)
    ]


def test_instrument_info_computes_mean_price():
    info = build_instrument_timeframe_info("EUR/USD", "h1", _candles([1.10, 1.11, 1.12]))
    assert info.mean_price == pytest.approx(1.11)


def test_instrument_info_unavailable_broker_fields_are_none_not_fabricated():
    info = build_instrument_timeframe_info("XAU/USD", "h1", _candles([1500.0, 1510.0]))
    assert info.tick_size is None
    assert info.tick_value is None
    assert info.minimum_position_size is None


def test_instrument_info_empty_candles_rejected():
    with pytest.raises(ValueError):
        build_instrument_timeframe_info("EUR/USD", "h1", [])


def test_notionally_comparable_position_size_matches_phase13_derivation():
    eur_info = build_instrument_timeframe_info("EUR/USD", "h1", _candles([1.1812433282986112]))
    xau_info = build_instrument_timeframe_info("XAU/USD", "h1", _candles([1423.4905500000002]))
    corrected = compute_notionally_comparable_position_size(eur_info, xau_info, reference_position_size=10000.0)
    assert corrected == pytest.approx(8.298216860650118, rel=1e-9)


def test_notional_position_size_rejects_zero_price():
    eur_info = build_instrument_timeframe_info("EUR/USD", "h1", _candles([1.10]))
    bad_info = build_instrument_timeframe_info("BAD", "h1", _candles([0.0]))
    with pytest.raises(ValueError):
        compute_notionally_comparable_position_size(eur_info, bad_info, 10000.0)


def test_paper_candidate_is_tradeable():
    config = make_config(gate_status="PAPER_CANDIDATE")
    result = select_strategy("XAU/USD", "h1", [config])
    assert result.status == "TRADEABLE"
    assert result.selected_config_id == config.config_id


def test_promising_is_not_tradeable():
    config = make_config(gate_status="PROMISING")
    result = select_strategy("XAU/USD", "h1", [config])
    assert result.status == "PROMISING_NOT_TRADEABLE"
    assert result.status != "TRADEABLE"


def test_rejected_candidate_excluded_yields_no_validated_edge():
    config = make_config(gate_status="REJECT_EARLY")
    result = select_strategy("XAU/USD", "h1", [config])
    assert result.status == "NO_VALIDATED_EDGE"


def test_no_configs_at_all_yields_no_validated_edge():
    result = select_strategy("EUR/USD", "h1", [])
    assert result.status == "NO_VALIDATED_EDGE"
    assert "No researched strategy" in result.reason


def test_research_required_status():
    config = make_config(gate_status="ROBUSTNESS_REQUIRED")
    result = select_strategy("XAU/USD", "h1", [config])
    assert result.status == "RESEARCH_REQUIRED"


def test_regime_incompatibility_excludes_candidate():
    config = make_config(gate_status="PAPER_CANDIDATE", regime_evidence={"HIGH_VOLATILITY": 158})
    result = select_strategy("XAU/USD", "h1", [config], current_regime="RANGING")
    assert result.status == "NO_VALIDATED_EDGE"
    assert "regime" in result.reason.lower() or "RANGING" in result.reason


def test_regime_compatible_when_evidence_exists():
    config = make_config(gate_status="PAPER_CANDIDATE", regime_evidence={"HIGH_VOLATILITY": 158})
    result = select_strategy("XAU/USD", "h1", [config], current_regime="HIGH_VOLATILITY")
    assert result.status == "TRADEABLE"


def test_instrument_timeframe_mismatch_excluded():
    config = make_config(instrument="GBP/USD", gate_status="PAPER_CANDIDATE")
    result = select_strategy("XAU/USD", "h1", [config])
    assert result.status == "NO_VALIDATED_EDGE"


def test_never_selects_by_highest_pf_only_by_gate_rank():
    rejected = make_config(config_id="vsc_a", gate_status="REJECT_EARLY")
    promising = make_config(config_id="vsc_b", gate_status="PROMISING")
    result = select_strategy("XAU/USD", "h1", [rejected, promising])
    assert result.status == "PROMISING_NOT_TRADEABLE"
    assert result.selected_config_id == "vsc_b"


def test_auditable_reasons_present_for_every_considered_candidate():
    config = make_config(gate_status="PROMISING")
    result = select_strategy("XAU/USD", "h1", [config])
    assert len(result.considered) == 1
    assert result.considered[0].config_id == config.config_id
    assert result.considered[0].reason


def test_deterministic_selection_repeated_calls():
    config = make_config(gate_status="PAPER_CANDIDATE")
    first = select_strategy("XAU/USD", "h1", [config])
    second = select_strategy("XAU/USD", "h1", [config])
    assert first == second


def test_no_validated_edge_includes_research_recommendation():
    result = select_strategy("EUR/USD", "h1", [])
    assert result.research_recommendation is not None


def test_tradeable_has_no_further_research_recommendation():
    config = make_config(gate_status="PAPER_CANDIDATE")
    result = select_strategy("XAU/USD", "h1", [config])
    assert result.research_recommendation is None
