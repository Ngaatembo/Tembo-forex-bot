# research/results/

Output from `backend/scripts/run_real_historical_validation.py`.

## Files here

- **`phase_4_5_summary.json`** — metadata (data source, license, SHA256
  hash of the source CSV, period covered, data-quality audit) plus
  summary metrics (win rate, profit factor, drawdown, etc.) for every
  cost tier and chronological period. Small, safe to commit.
- **`phase_4_5_base_cost_trades.json`** — the full 1,539-trade record
  (entry/exit price/time, P&L, exit reason) for the realistic BASE_COST
  full-period run. ~950KB, kept for auditability.

## What's NOT here, and why

The full per-candle equity curve (all cost tiers x 57,600 candles) is
**not** committed — it's ~72MB, and per the project's own instruction
not to commit large datasets into the repo, it isn't worth the repo
bloat. It's fully reproducible: rerun the script below and it's
regenerated from scratch, byte-identical, since the engine is
deterministic (see `docs/phase-4-notes.md`).

## Reproducing this exact run

The source dataset is NOT included in this repo either (same reasoning
— it's someone else's dataset, freely available, no need to duplicate
it here). To reproduce:

```bash
curl -o EURUSDh1.csv \
  https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/EURUSD/EURUSDh1.csv

cd backend
python -m scripts.run_real_historical_validation \
  --csv ../EURUSDh1.csv \
  --output-dir ../research/results
```

Verify you have the exact same dataset this run used by checking the
SHA256 hash recorded in `phase_4_5_summary.json` against your
downloaded file:

```bash
sha256sum EURUSDh1.csv
```

See `docs/phase-4-5-real-historical-validation.md` for the full
write-up and interpretation of these results.
