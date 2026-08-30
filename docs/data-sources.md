# Data Sources

## Market data

Phase 0/1 ships with `MockMarketDataProvider` only — no network calls,
no credentials required. Candidate real providers to evaluate in
Phase 1 (availability varies by jurisdiction — verify before
integrating):

- OANDA
- IG
- FXCM
- Interactive Brokers

## News

No provider selected yet (Phase 5). Requirements: preserves original
publication timestamp (critical for preventing look-ahead bias in
backtests), provides source/URL, ideally tags affected currency/asset.

## Economic calendar

No provider selected yet (Phase 5). Must distinguish `actual` /
`forecast` / `previous` values per event and support surprise-metric
calculation.

## Initial instrument scope (v1)

- EUR/USD
- GBP/USD
- USD/JPY
- XAU/USD

Architecture must stay extensible to more instruments without a rewrite.
