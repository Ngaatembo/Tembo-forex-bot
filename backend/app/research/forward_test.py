"""
Forward testing of PROMISING strategies on paper / Deriv demo only.

A strategy whose research gate is PROMISING is normally not tradeable.
The owner can explicitly allow named configurations (DEMO_FORWARD_TEST_CONFIGS)
to trade on the simulated paper account and the Deriv *demo* account, so the
strategy collects fresh out-of-sample evidence. This never widens anything
else: the live signal must trigger, macro risk must pass and the full risk
hierarchy must approve. Forward tests use half the normal per-trade risk.
Nothing here can reach a real-money account.
"""

from dataclasses import replace

from app.core.config import get_settings
from app.risk_engine.risk_models import RiskLimitsConfig

FORWARD_TEST_MAX_RISK_PER_TRADE = 0.005


def forward_test_config_ids() -> frozenset[str]:
    raw = get_settings().demo_forward_test_configs or ""
    ids = {item.strip() for item in raw.split(",")}
    return frozenset(i for i in ids if i and i.lower() != "none")


def is_forward_test(status: str | None, selected_config_id: str | None, allowed: frozenset[str]) -> bool:
    return (
        status == "PROMISING_NOT_TRADEABLE"
        and selected_config_id is not None
        and selected_config_id in allowed
    )


def forward_test_limits(limits: RiskLimitsConfig) -> RiskLimitsConfig:
    return replace(
        limits,
        max_risk_per_trade_pct=min(limits.max_risk_per_trade_pct, FORWARD_TEST_MAX_RISK_PER_TRADE),
    )
