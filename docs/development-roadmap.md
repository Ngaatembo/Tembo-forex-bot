# Development Roadmap

Build order — do not skip ahead. Each phase should be working and
tested before the next begins.

| Phase | Goal |
|---|---|
| 0 | Repo structure, config, DB schema foundation, health endpoint — **current** |
| 1 | Market data: provider abstraction + real historical data for EUR/USD stored in PostgreSQL |
| 2 | Technical engine: indicators, regime detection, volatility, momentum |
| 3 | Basic strategies (trend, breakout, mean reversion) generating signals without AI |
| 4 | Backtesting: realistic costs, performance metrics, determine if basic strategies have any historical edge |
| 5 | News + economic data collection, sentiment, event surprise |
| 6 | AI analysis engine: structured interpretation, historical analogues |
| 7 | Multi-factor strategy combining technical + news + macro + regime |
| 8 | Paper trading with live data and simulated money |
| 9 | Full dashboard |
| 10 | Live trading — only after extensive validation, extremely limited exposure, hard risk limits, kill switch, full logging |

## Non-negotiable rules

1. Never promise profitability.
2. Never assume AI predictions are correct.
3. Never use future information in historical tests.
4. Never optimize solely for historical profit.
5. Never allow AI to bypass risk management.
6. Never connect live money during early development.
7. Never hard-code API keys.
8. Never hide losing trades from performance reports.
9. Never delete historical trade records to improve statistics.
10. Every strategy must be independently measurable.
11. Every major decision must be explainable from stored data.
12. Prefer WAIT over low-quality trades.
13. Build the smallest working version before adding complexity.
14. Keep live execution completely isolated from research/backtesting.
15. Document assumptions.
