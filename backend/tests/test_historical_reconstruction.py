from app.research.historical_reconstruction import (
    backtest_summary_from_dict, cost_tier_summaries_from_h1_robustness,
    cost_tier_summaries_from_phase9_results, parameter_neighborhood_from_h1_robustness,
    period_summaries_from_metrics, period_summaries_from_phase9_tier,
    regime_dependence_from_h1_robustness, statistical_evidence_from_h1_robustness,
)


def minimal_summary_dict(**overrides) -> dict:
    d = dict(
        initial_balance=10000.0, final_balance=10000.0, net_pnl=0.0, total_return=0.0,
        trade_count=100, winning_trades=50, losing_trades=50, win_rate=0.5,
        average_win=100.0, average_loss=-100.0, largest_win=200.0, largest_loss=-200.0,
        average_trade=0.0, expectancy=0.0, max_consecutive_wins=5, max_consecutive_losses=5,
        profit_factor=1.0, max_drawdown=1000.0, max_drawdown_percent=0.10,
    )
    d.update(overrides)
    return d


def test_backtest_summary_from_dict():
    s = backtest_summary_from_dict(minimal_summary_dict(profit_factor=1.234))
    assert s.profit_factor == 1.234


def test_period_summaries_from_metrics_phase8_shape():
    metrics = {
        "development": minimal_summary_dict(profit_factor=1.1),
        "validation": minimal_summary_dict(profit_factor=1.2),
        "out_of_sample": minimal_summary_dict(profit_factor=1.0),
    }
    result = period_summaries_from_metrics(metrics)
    assert result["development"].profit_factor == 1.1
    assert result["out_of_sample"].profit_factor == 1.0


def test_period_summaries_from_phase9_tier_shape():
    """Phase 9's shape nests an extra 'summary' key alongside payoff/holding stats."""
    tier_data = {
        "development": {"summary": minimal_summary_dict(profit_factor=0.9), "payoff_ratio": 2.5, "mean_holding_hours": 20.0},
        "out_of_sample": {"summary": minimal_summary_dict(profit_factor=0.85), "payoff_ratio": 2.3, "mean_holding_hours": 18.0},
    }
    result = period_summaries_from_phase9_tier(tier_data)
    assert result["development"].profit_factor == 0.9
    assert result["out_of_sample"].profit_factor == 0.85


def test_cost_tier_summaries_from_h1_robustness():
    cost_sensitivity = {
        "LOW": {"out_of_sample": minimal_summary_dict(profit_factor=1.04)},
        "BASE": {"out_of_sample": minimal_summary_dict(profit_factor=1.00)},
        "HIGH": {"out_of_sample": minimal_summary_dict(profit_factor=0.91)},
    }
    result = cost_tier_summaries_from_h1_robustness(cost_sensitivity)
    assert result["LOW"].profit_factor == 1.04
    assert result["HIGH"].profit_factor == 0.91


def test_cost_tier_summaries_from_phase9_results_ignores_non_tier_keys():
    lookback_results = {
        "LOW": {"out_of_sample": {"summary": minimal_summary_dict(profit_factor=0.83)}},
        "BASE": {"out_of_sample": {"summary": minimal_summary_dict(profit_factor=0.81)}},
        "HIGH": {"out_of_sample": {"summary": minimal_summary_dict(profit_factor=0.76)}},
        "verdict_base_cost": "REJECTED",  # a real non-tier key present in the actual file — must be skipped
    }
    result = cost_tier_summaries_from_phase9_results(lookback_results)
    assert set(result.keys()) == {"LOW", "BASE", "HIGH"}
    assert result["BASE"].profit_factor == 0.81


def test_parameter_neighborhood_selects_only_matching_prefix():
    neighborhood_results = {
        "distance_0.0004": {"out_of_sample": minimal_summary_dict(profit_factor=1.036)},
        "distance_0.0005": {"out_of_sample": minimal_summary_dict(profit_factor=1.000)},
        "distance_0.0006": {"out_of_sample": minimal_summary_dict(profit_factor=0.880)},
        "atr_ceiling_0.0012": {"out_of_sample": minimal_summary_dict(profit_factor=0.902)},
    }
    result = parameter_neighborhood_from_h1_robustness(neighborhood_results, prefix="distance_")
    assert len(result) == 3
    assert {round(s.profit_factor, 3) for s in result} == {1.036, 1.000, 0.880}


def test_statistical_evidence_maps_key_names_correctly():
    statistical_analysis = {
        "wilson_95_ci": [0.6038, 0.7194],
        "bootstrap_95_ci_total_pnl": [-1714.0, 1596.8],
        "breakeven_win_rate": 0.6667,
    }
    result = statistical_evidence_from_h1_robustness(statistical_analysis, actual_win_rate=0.664)
    assert result["wilson_ci"] == (0.6038, 0.7194)
    assert result["bootstrap_ci_total_pnl"] == (-1714.0, 1596.8)
    assert result["breakeven_win_rate"] == 0.6667
    assert result["actual_win_rate"] == 0.664


def test_regime_dependence_passthrough():
    regime_dependence = {"TRENDING_UP": {"net_pnl": 190.3, "trade_count": 42}}
    result = regime_dependence_from_h1_robustness(regime_dependence)
    assert result == regime_dependence
