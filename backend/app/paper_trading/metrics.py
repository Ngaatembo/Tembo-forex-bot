from collections import Counter, defaultdict


def build_runtime_metrics(events, trade_rows):
    """Build deterministic metrics from persistent paper-runtime evidence."""
    status_counts = Counter(str(e.get("status", "UNKNOWN")) for e in events)
    rejection_counts = Counter()
    instrument_counts = Counter()

    for event in events:
        status = str(event.get("status", "UNKNOWN"))
        if status not in {"CLOSED", "WAITING_NEW_CANDLE", "NO_SIGNAL"}:
            rejection_counts[str(event.get("reason") or "unspecified")] += 1
        instrument = event.get("instrument")
        if instrument:
            instrument_counts[str(instrument)] += 1

    pnl_values = [float(t.realized_pnl) for t in trade_rows]
    total_pnl = sum(pnl_values)
    wins = sum(1 for pnl in pnl_values if pnl > 0)
    losses = sum(1 for pnl in pnl_values if pnl < 0)
    gross_profit = sum(pnl for pnl in pnl_values if pnl > 0)
    gross_loss = sum(pnl for pnl in pnl_values if pnl < 0)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else None

    by_instrument = defaultdict(lambda: {
        "trades": 0, "realized_pnl": 0.0, "wins": 0, "losses": 0
    })
    for trade, pnl in zip(trade_rows, pnl_values):
        bucket = by_instrument[trade.instrument]
        bucket["trades"] += 1
        bucket["realized_pnl"] += pnl
        bucket["wins"] += int(pnl > 0)
        bucket["losses"] += int(pnl < 0)

    return {
        "mode": "PAPER_ONLY",
        "cycles_observed": len({e.get("cycle_at") for e in events if e.get("cycle_at")}),
        "events_observed": len(events),
        "decision_status_counts": dict(status_counts),
        "rejection_reason_counts": dict(rejection_counts.most_common(25)),
        "instrument_event_counts": dict(instrument_counts),
        "performance": {
            "closed_trades": len(trade_rows),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(trade_rows)) if trade_rows else None,
            "realized_pnl": total_pnl,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "by_instrument": dict(by_instrument),
        },
        "execution_enabled": False,
        "broker_contacted": False,
        "note": "Metrics use only persistent runtime events and immutable closed paper trades; no estimates are generated.",
    }
