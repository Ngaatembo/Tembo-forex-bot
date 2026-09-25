"""Re-scores Experiment 3B trades as R-multiples (profit divided by the ATR-2x stop risk at entry)
and compounds them at a fixed 1% account risk per trade — the Risk Engine's deployed default.
Same trades, same costs; only the position sizing view changes."""
import json, sys
sys.path.insert(0, ".")
from scripts.run_experiment_3b_gold_real_costs import load_old, load_new, run
from app.technical_engine.features import calculate_feature_snapshots

def rscore(candles, name, tier="BASE", risk=0.01):
    feats = calculate_feature_snapshots(candles)
    atr_at = {f.timestamp: f.atr_14 for f in feats}
    res = run(name, candles, feats, tier)
    eq, peak, mdd, rs = 1.0, 1.0, 0.0, []
    for t in res.trades:
        atr = atr_at.get(t.signal_timestamp)
        if not atr:
            continue
        r = (t.net_pnl / t.size) / (2.0 * atr)
        rs.append(r)
        eq *= (1 + risk * r); peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
    years = (candles[-1].timestamp - candles[0].timestamp).days / 365.25
    return {"trades": len(rs), "avg_R": sum(rs) / len(rs), "total_return_pct": (eq - 1) * 100,
            "annualised_pct": (eq ** (1 / years) - 1) * 100, "max_drawdown_pct": mdd * 100,
            "worst_R": min(rs), "best_R": max(rs), "years": round(years, 2)}

if __name__ == "__main__":
    out = {}
    for label, c in (("history_2012_2022", load_old(sys.argv[1])), ("forward_2024_2026", load_new(sys.argv[2]))):
        out[label] = {}
        for n in ("breakout_30", "breakout_40", "breakout_50"):
            out[label][n] = {tier: rscore(c, n, tier) for tier in ("BASE", "HIGH")}
            print(label, n, {k: round(v, 2) for k, v in out[label][n]["BASE"].items()})
    json.dump(out, open(sys.argv[3], "w"), indent=1)
