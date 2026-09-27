# Risk Management

## Principle

Risk management operates independently from AI and strategy. AI output cannot bypass risk controls. If risk state is unknown, the system does not trade — this is enforced in code, not only documented as policy.

## Configurable limits

- Max risk per trade
- Max daily loss
- Max weekly loss
- Max drawdown
- Max open positions
- Max leverage
- Correlated exposure limits as instrument support expands
- Minimum risk/reward thresholds where configured
- Emergency kill switch

## Live execution gate

Two independent conditions must both be true before any real-money order can be placed:

1. ENABLE_LIVE_EXECUTION=true is explicitly set.
2. A real BrokerAdapter implementation exists and is registered.

At present, condition 2 is deliberately not satisfied. get_broker_adapter() fails closed rather than silently converting a configuration flag into live trading.

Before live execution is ever enabled, the broker adapter must also pass demo-account connectivity, order-parameter, rejection, timeout, duplicate-order and emergency-stop tests.

## Fail closed

Risk checks return BLOCKED or UNKNOWN by default. OK must be actively earned by passing validation; it is never the fallback for missing values, exceptions or unrecognized state.
