"""
Stop-loss validation. Never corrects an invalid stop — returns an
auditable rejection reason instead.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StopValidationResult:
    valid: bool
    reason: str


def validate_stop(direction: str, entry_price: float, stop_price: Optional[float]) -> StopValidationResult:
    if stop_price is None:
        return StopValidationResult(False, "Missing stop-loss — a trade proposal without a stop is never valid.")
    if entry_price <= 0 or stop_price <= 0:
        return StopValidationResult(False, f"Entry ({entry_price}) and stop ({stop_price}) prices must both be positive.")

    if direction == "LONG":
        if stop_price >= entry_price:
            return StopValidationResult(False, f"LONG stop ({stop_price}) must be below entry ({entry_price}) — stop is on the wrong side.")
        actual_distance = entry_price - stop_price
    elif direction == "SHORT":
        if stop_price <= entry_price:
            return StopValidationResult(False, f"SHORT stop ({stop_price}) must be above entry ({entry_price}) — stop is on the wrong side.")
        actual_distance = stop_price - entry_price
    else:
        return StopValidationResult(False, f"Unknown direction {direction!r} — must be 'LONG' or 'SHORT'.")

    if actual_distance <= 0:
        return StopValidationResult(False, "Zero-distance stop — entry and stop cannot be equal.")

    return StopValidationResult(True, f"Stop valid: {actual_distance:.6f} price units from entry.")
