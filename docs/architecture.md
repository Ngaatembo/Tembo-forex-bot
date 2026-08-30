# Architecture

## Data flow

```
Market Data -> Data Storage (PostgreSQL) -> Analysis Engine (technical)
News/Macro -> News Engine -> Sentiment/Event Analysis
                                    |
                                    v
                            AI Analysis Engine (interprets, does not decide)
                                    |
                                    v
                            Strategy Engine (trend / breakout / mean-reversion / news)
                                    |
                                    v
                            Signal Engine (BUY / SELL / WAIT)
                                    |
                                    v
                            Risk Management Engine (fail-closed gate)
                                    |
                                    v
                    Backtesting <-----+-----> Paper Trading
                                    |
                                    v
                          Performance Analytics -> Dashboard
                                    |
                                    v
                    Controlled Live Execution (future, opt-in only)
```

## Module responsibilities

| Module | Responsibility | Phase |
|---|---|---|
| `data_engine` | Provider-agnostic market data access | 1 |
| `technical_engine` | Indicators, regime detection, volatility | 2 |
| `strategy_engine` | Trend/breakout/mean-reversion/news strategies | 3 |
| `backtesting` | Historical simulation, metrics, validation | 4 |
| `news_engine` | News collection, sentiment, event impact | 5 |
| `ai_engine` | Structured AI interpretation (not execution) | 6 |
| `signal_engine` | Unified BUY/SELL/WAIT signal generation | 6-7 |
| `risk_engine` | Position sizing, limits, kill switch | 21 (ongoing) |
| `paper_trading` | Realistic simulated-money trading | 8 |
| `execution` | Broker adapter (paper only until Phase 10) | 8/10 |

## Key design decisions

- **Provider abstraction everywhere.** `MarketDataProvider`, news
  providers, and `BrokerAdapter` are all interfaces. Nothing in the
  strategy/signal/risk layers imports a vendor SDK directly.
- **AI is advisory, not authoritative.** The AI analysis engine
  returns structured output (direction, confidence, reasons,
  invalidating conditions). It cannot place an order and cannot
  bypass the risk engine.
- **Risk engine fails closed.** `risk_engine/kill_switch.py` returns
  `BLOCKED` on any unknown state. Every future order-placing path
  must call through it first.
- **Backtesting and live execution are structurally isolated**
  (separate modules, separate broker adapters) so a bug in one
  cannot silently affect the other.
