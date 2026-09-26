from types import SimpleNamespace


from app.paper_trading.metrics import build_runtime_metrics


def trade(instrument, pnl):
    return SimpleNamespace(instrument=instrument, realized_pnl=pnl)


def test_runtime_metrics_empty_state_is_zeroed():
    result = build_runtime_metrics([], [])

    assert result["mode"] == "PAPER_ONLY"
    assert result["cycles_observed"] == 0
    assert result["events_observed"] == 0
    assert result["performance"]["closed_trades"] == 0
    assert result["performance"]["win_rate"] is None
    assert result["performance"]["profit_factor"] is None
    assert result["execution_enabled"] is False
    assert result["broker_contacted"] is False


def test_runtime_metrics_aggregates_trades_and_events():
    events = [
        {"cycle_at": "2026-09-26T04:00:00Z", "instrument": "EUR/USD", "status": "NO_SIGNAL"},
        {"cycle_at": "2026-09-26T04:00:00Z", "instrument": "GBP/USD", "status": "NO_VALIDATED_EDGE", "reason": "gate closed"},
        {"cycle_at": "2026-09-26T04:15:00Z", "instrument": "EUR/USD", "status": "NO_VALIDATED_EDGE", "reason": "gate closed"},
    ]
    trades = [trade("EUR/USD", 20), trade("EUR/USD", -10), trade("XAU/USD", 5)]

    result = build_runtime_metrics(events, trades)

    assert result["cycles_observed"] == 2
    assert result["events_observed"] == 3
    assert result["decision_status_counts"] == {
        "NO_SIGNAL": 1,
        "NO_VALIDATED_EDGE": 2,
    }
    assert result["rejection_reason_counts"] == {"gate closed": 2}
    assert result["instrument_event_counts"] == {"EUR/USD": 2, "GBP/USD": 1}
    assert result["performance"]["closed_trades"] == 3
    assert result["performance"]["wins"] == 2
    assert result["performance"]["losses"] == 1
    assert result["performance"]["win_rate"] == 2 / 3
    assert result["performance"]["realized_pnl"] == 15
    assert result["performance"]["gross_profit"] == 25
    assert result["performance"]["gross_loss"] == -10
    assert result["performance"]["profit_factor"] == 2.5
    assert result["performance"]["by_instrument"]["EUR/USD"]["realized_pnl"] == 10
    assert result["performance"]["by_instrument"]["XAU/USD"]["wins"] == 1
