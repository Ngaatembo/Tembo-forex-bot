# Experiment 3B — Gold with real costs + unseen 2024–2026 data (25 Sep 2026)

## Why

1. **Cost bug.** Every gold result before this (Phases 13, 13.1, Edge Validation 1 & 2) used the forex cost tiers:
   spread `0.0001`, slippage `0.00002` in price units. For gold that is **$0.0001 per ounce**, i.e. free trading.
   Real gold spreads are ~$0.15–$0.60/oz. That is why Phase 13.1 reported results "unchanged at HIGH cost".
2. **Experiment 3 as written could not run.** Its walk-forward window needs 1,400 days; 2023+ data is shorter than one
   window. Its loader also passed a dict where `CSVImportConfig` is required. Experiment 3B replaces it with a frozen
   forward test: the configurations already marked PROMISING (breakout 30/40/50, ATR 2x stop, 100-candle max hold) are
   run on 2024–2026 data with **no re-tuning**.

## Data

- 2012-05 → 2022-03: `ejtraderLabs/historical-data` XAUUSDh1.csv (same file as all earlier phases).
- 2024-01-01 → 2026-09-15: 15,453 hourly mid-price candles built from ~190M bid/ask ticks
  (`simom1/XAUUSD-history`, rebuilt by `scripts/build_xauusd_h1_from_ticks.py`; not committed, no licence published).
  Fixes: 32.5M ticks quoted 100x too small were rescaled; spreads >$5 dropped; corrupt Oct-2025 file skipped
  (gap 2025-10-20 → 11-02); source gap 2026-04-21 → 05-01.
- Measured median spread: **$0.20 (2024), $0.16 (2025), $0.26 (2026)** per oz.

## Cost tiers used ($/oz)

| Tier | Spread | Slippage per side |
|---|---|---|
| ORIGINAL_FOREX_TIER (old, for comparison) | 0.0001 | 0.00002 |
| LOW | 0.20 | 0.02 |
| BASE | 0.35 | 0.05 |
| HIGH | 0.60 | 0.10 |

## Results (BASE cost, 8.3 oz fixed position, $10k account)

| Strategy | 2012–22 old cost PF | 2012–22 real cost PF | 2024–26 unseen PF | 2024–26 trades | Long PF | Short PF |
|---|---|---|---|---|---|---|
| Breakout 30 | 1.165 | 1.100 | 1.252 | 317 | 1.81 | 0.81 |
| Breakout 40 | 1.146 | 1.086 | 1.357 | 272 | 1.81 | 0.92 |
| Breakout 50 | 1.135 | 1.077 | 1.285 | 244 | 1.84 | 0.76 |

- Neighbours also positive on 2024–26: breakout 20 PF 1.23, breakout 60 PF 1.42.
- Buy-and-hold of the same 8.3 oz over 2024–26: **+$18,414** vs breakout 40 **+$13,792** (max drawdown 33%).
- Breakout 40 by half-year: 2024-H1 −$1,623, then positive in every half-year after.
- Bootstrap 95% CI on total P&L still includes zero (2024–26 breakout 40: −$3,909 to +$33,577).

### Re-scored at 1% account risk per trade (R-multiples vs the ATR-2x stop, compounded)

| Strategy | 2012–22 per year | 2012–22 worst drawdown | 2024–26 per year | 2024–26 worst drawdown |
|---|---|---|---|---|
| Breakout 30 | 6.6% | 52.8% | 14.8% | 17.8% |
| Breakout 40 | 5.8% | 48.9% | 27.4% | 22.2% |
| Breakout 50 | 5.9% | 27.5% | 11.0% | 27.5% |

### Fragility

- The **5 best trades** made 135% (2012–22) and 98% (2024–26) of breakout 40's total profit. Without them:
  −$1,333 and +$318.
- Longest losing streak: 15 trades (2012–22), 11 (2024–26). Win rate ~26–29%. Median hold ~30–35 hours; ~8 trades/month.

## Verdict: REGIME_DEPENDENT_EDGE

The breakout edge **survived real costs and held on unseen 2024–26 data**, but:
- 2024–26 profit came from **long** trades during gold's run from ~$2,064 to ~$4,284; shorts lost.
- A handful of big trades carry everything, so a live system that misses even one breakout (downtime, a missed
  hourly run) can lose a year's edge.
- Historical drawdowns at 1% risk (~50%) exceed the Risk Engine's own 15% max-drawdown limit.

**Next step:** live paper trading of breakout 40 on XAU/USD H1 with reliable hourly execution, at ≤0.5% risk per trade.
Not real money.

Historical and out-of-sample results do not guarantee future profitability.

Reproduce:
```bash
python -m scripts.run_experiment_3b_gold_real_costs --old ../data/XAUUSDh1.csv --new ../data/XAUUSD_H1_2024plus_with_spread.csv --out ../research/results/experiment_3b_gold_real_costs.json
python -m scripts.exp3b_risk_sizing ../data/XAUUSDh1.csv ../data/XAUUSD_H1_2024plus_with_spread.csv ../research/results/experiment_3b_risk_sized.json
```
