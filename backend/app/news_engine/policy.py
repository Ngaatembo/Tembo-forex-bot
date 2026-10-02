"""Shared policy for how macro-event risk affects trade eligibility.

The macro risk engine reports context. This module is the single policy
decision used by live, paper, and alert paths so they cannot drift apart.
HIGH risk blocks trade eligibility. MEDIUM is informational by design.
UNKNOWN is not silently treated as safe; callers must surface it as data
quality/status information and may fail closed when their required data is unavailable.
"""

def macro_blocks_trade(level: str) -> bool:
    """Return whether macro risk itself blocks a trade."""
    return level == "HIGH"
