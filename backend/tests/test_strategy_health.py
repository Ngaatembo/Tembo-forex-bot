from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig


def _config(**overrides):
    data = {
        "config_id": "cfg",
        "candidate_id": "cand",
        "instrument": "XAU/USD",
        "timeframe": "h1",
        "strategy_family": "breakout",
        "parameters": {},
        "exit_config_summary": {},
        "cost_assumptions": {"tier": "BASE"},
        "evidence_period_start": "2024-01-01T00:00:00+00:00",
        "evidence_period_end": "2024-12-31T23:00:00+00:00",
        "gate_status": "PROMISING",
        "verdict": "PROMISING",
        "statistical_level": "WEAK",
        "regime_evidence": {"HIGH_VOLATILITY": 10},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    data.update(overrides)
    return ValidatedStrategyConfig(**data)


def test_strategy_health_preserves_promising_not_tradeable():
    result = select_strategy("XAU/USD", "h1", [_config()])
    assert result.status == "PROMISING_NOT_TRADEABLE"
    assert result.selected_config_id == "cfg"
    assert result.research_recommendation


def test_strategy_health_excludes_regime_incompatible_config():
    result = select_strategy(
        "XAU/USD",
        "h1",
        [_config()],
        current_regime="TRENDING",
    )
    assert result.status == "NO_VALIDATED_EDGE"
    assert result.selected_config_id is None
    assert "incompatible" in result.reason


def test_strategy_health_accepts_paper_candidate_only():
    result = select_strategy(
        "EUR/USD",
        "h1",
        [_config(
            config_id="paper_cfg",
            instrument="EUR/USD",
            gate_status="PAPER_CANDIDATE",
            statistical_level="STRONG",
            regime_evidence={"TRENDING": 20},
        )],
        current_regime="TRENDING",
    )
    assert result.status == "TRADEABLE"
    assert result.selected_config_id == "paper_cfg"
