# Tembo — Market Intelligence, Research & Paper-Trading Platform

Tembo is a modular trading-research platform for verified market data, technical analysis, macro/news context, strategy research, risk evaluation and paper trading.

**Current boundary:** Tembo is **not a live-money trading bot**. Live execution is deliberately fail-closed because a real broker execution adapter has not been registered. Setting the live flag alone cannot place an order.

## Current architecture

```
Verified market provider
        ↓
Normalization + data-quality validation
        ↓
Candles / technical analysis / candlestick context
        ↓
News + economic-calendar context
        ↓
Multi-factor decision
        ↓
Validated-strategy gate
        ↓
Risk engine / kill switch
        ↓
Paper-trading eligibility
        ↓
Paper runtime / analytics

Live execution
        ↓
BLOCKED until a real broker adapter is implemented,
registered, tested and explicitly enabled.
```

## Market coverage

The live cockpit supports the following timeframes:

- M5
- M15
- H1
- H4
- D1

Core instruments include EUR/USD, GBP/USD and XAU/USD. Deriv synthetic indices use the `SYNTH:<DerivSymbol>` format and are discovered from Deriv's public market-data endpoint.

The cockpit refuses mock data when a live market view is requested. Provider candles are normalized and validated before being exposed as live market data.

## Providers

The codebase contains provider adapters for:

- OANDA
- Twelve Data
- Deriv synthetic-index market data
- MT5 bridge scaffolding
- News/calendar providers

Provider availability depends on runtime configuration and credentials. A provider existing in code does not mean it is connected in production.

## Safety boundary

The following are intentional hard boundaries:

1. AI output cannot bypass the risk engine.
2. Invalid or unknown risk state fails closed.
3. Mock market data is never presented as verified live data.
4. The live cockpit does not place orders.
5. Live execution requires both explicit configuration and a registered real broker adapter.
6. Paper trading and live execution remain separate.
7. Historical research must not use future information.

See `docs/architecture.md` and `docs/risk-management.md` for the contracts.

## Development

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

Run the backend tests with:

```bash
cd backend
pytest -q
```

## Project status

The repository has moved beyond the original Phase-0 skeleton. The README is intentionally kept aligned with the implemented architecture; unfinished integrations are labelled as such instead of being described as complete.

**Not ready for live-money trading:** the real broker execution adapter and its end-to-end demo-account validation are still required.
