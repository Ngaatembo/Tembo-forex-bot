# Risk Management

## Principle

Risk management operates independently from the AI and from any
strategy. The AI cannot bypass risk controls. If risk state is
unknown, the system does not trade — this is enforced in code, not
just documented as policy (`app/risk_engine/kill_switch.py`).

## Configurable limits (see `.env.example`)

- Max risk per trade (%)
- Max daily loss (%)
- Max weekly loss (%)
- Max drawdown (%)
- Max open positions
- Max leverage
- Max correlated exposure (per-currency) — Phase 7+
- Minimum risk/reward threshold — Phase 3+
- Trading pause after repeated losses — Phase 8+
- Emergency kill switch — scaffolded now, real logic added as trading
  logic itself is built, phase by phase

## Live execution gate

Two independent conditions must both be true before any real-money
order can be placed:

1. `ENABLE_LIVE_EXECUTION=true` in environment configuration
2. A real `BrokerAdapter` implementation exists and is registered in
   `app/execution/broker_adapter.py`

As of Phase 0, condition 2 is not met — no live adapter exists.
`get_broker_adapter()` always returns `PaperBrokerAdapter` today,
and will keep doing so even if condition 1 is flipped, until a real
adapter is deliberately written.

## What "fail closed" means here

Every function in the risk-check path returns a `BLOCKED` or
`UNKNOWN` result by default. `OK` must be actively earned by a
passing check — it is never the fallback on an exception, a missing
value, or an unrecognized state.
