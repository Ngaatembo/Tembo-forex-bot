"""
Builds and persists the canonical ValidatedStrategyConfig registry the
API reads at request time. Reuses Phase 14's exact builder functions
(build_eurusd_configs, build_gbpusd_configs, build_xauusd_configs)
UNCHANGED — this script only adds persistence, no new evidence, no
new backtests.
"""

import json
import sys

sys.path.insert(0, "scripts")
from run_phase14_demonstration import build_eurusd_configs, build_gbpusd_configs, build_xauusd_configs

REGISTRY_PATH = "/home/claude/ai-trading-platform/research/results/validated_strategy_configs.json"


def main():
    configs = build_eurusd_configs() + build_gbpusd_configs() + build_xauusd_configs()
    with open(REGISTRY_PATH, "w") as f:
        json.dump([c.to_dict() for c in configs], f, indent=2, default=str)
    print(f"Persisted {len(configs)} ValidatedStrategyConfig records to {REGISTRY_PATH}")
    for c in configs:
        print(f"  {c.instrument} {c.timeframe} {c.strategy_family.value}: gate={c.gate_status}")


if __name__ == "__main__":
    main()
