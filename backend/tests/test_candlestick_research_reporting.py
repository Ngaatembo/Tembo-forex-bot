from scripts.run_candlestick_book_research import MIN_CANDIDATE_COUNT, net_return, summarize
import pandas as pd

def test_minimum_candidate_count_is_explicit():
    assert MIN_CANDIDATE_COUNT == 30

def test_net_return_reduces_gross_return_by_cost():
    gross = 0.001
    low = net_return(gross, 1.10, 0.5)
    high = net_return(gross, 1.10, 2.0)
    assert low > high
    assert high < gross

def test_summary_marks_thin_samples_insufficient_and_reports_net_costs():
    frame = pd.DataFrame({"signed_return": [0.001, -0.0002], "entry_price": [1.10, 1.10]})
    result = summarize(frame)
    assert result["sample_sufficient"] is False
    assert result["count"] == 2
    assert result["cost_scenarios"]["base"]["average_net_return"] < result["average_gross_return"]
