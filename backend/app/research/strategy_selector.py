"""
Strategy Selector — deterministic, read-only. Given an instrument,
timeframe, and a pool of ValidatedStrategyConfig snapshots, determines
whether a validated edge exists — and if not, says so explicitly
rather than defaulting to "trade something."

CORE PRINCIPLE (this is the entire point of this module): selection
is driven by Research Gate status, never by "which config had the
highest historical profit factor." A config with gate_status
REJECT_EARLY and a great-looking PF is never selected over a
PAPER_CANDIDATE with a modest one — the gate status already encodes
everything the evidence supports; re-deriving a competing "which
looks best" ranking from raw numbers would defeat the entire purpose
of building the gate in the first place.

NO_VALIDATED_EDGE is a SUCCESS state, not an error or an empty
result — it means the system correctly recognizes it has no business
recommending a trade here, exactly per the founding principle of this
phase.
"""

from dataclasses import dataclass
from typing import Optional

from app.research.validated_strategy_config import ValidatedStrategyConfig

_GATE_RANK = {
    "PAPER_CANDIDATE": 0,
    "PROMISING": 1,
    "ROBUSTNESS_REQUIRED": 2,
    "RESEARCH": 3,
    "REJECT_EARLY": 4,
    "CLOSED": 4,
}

_STATUS_FOR_GATE = {
    "PAPER_CANDIDATE": "TRADEABLE",
    "PROMISING": "PROMISING_NOT_TRADEABLE",
    "ROBUSTNESS_REQUIRED": "RESEARCH_REQUIRED",
    "RESEARCH": "RESEARCH_REQUIRED",
    "REJECT_EARLY": "NO_VALIDATED_EDGE",
    "CLOSED": "NO_VALIDATED_EDGE",
}


@dataclass(frozen=True)
class ConsideredCandidate:
    config_id: str
    gate_status: str
    reason: str


@dataclass(frozen=True)
class SelectionResult:
    instrument: str
    timeframe: str
    status: str
    selected_config_id: Optional[str]
    reason: str
    considered: tuple
    research_recommendation: Optional[str]


def _regime_compatible(config: ValidatedStrategyConfig, current_regime: Optional[str]) -> bool:
    if current_regime is None:
        return True
    return config.regime_evidence.get(current_regime, 0) > 0


def _research_recommendation_for(status: str, configs: list) -> Optional[str]:
    if status == "TRADEABLE":
        return None
    if status == "PROMISING_NOT_TRADEABLE":
        weak_stats = any(c.statistical_level in ("WEAK", "UNKNOWN") for c in configs)
        if weak_stats:
            return (
                "Grow the out-of-sample statistical sample (more trades or, ideally, genuinely "
                "fresh confirmation data) before this can advance past PROMISING."
            )
        return "Evidence is promising but not yet PAPER_CANDIDATE — review remaining Scorecard gaps."
    if status == "RESEARCH_REQUIRED":
        return "Insufficient or inconsistent evidence — this instrument/timeframe needs dedicated research before a recommendation can be made either way."
    if status == "NO_VALIDATED_EDGE" and not configs:
        return "No strategy has ever been tested on this instrument/timeframe. Testing an already-researched mechanism here is more efficient than inventing a new one."
    return "Every tested configuration for this instrument/timeframe was rejected. Consider testing an already-researched mechanism on a different instrument/timeframe rather than modifying a rejected one."


def select_strategy(
    instrument: str, timeframe: str, configs: list, current_regime: Optional[str] = None,
) -> SelectionResult:
    matching = [c for c in configs if c.instrument == instrument and c.timeframe == timeframe]

    considered = []
    eligible = []
    for c in matching:
        if not _regime_compatible(c, current_regime):
            considered.append(ConsideredCandidate(
                c.config_id, c.gate_status,
                f"Excluded: no trades observed in current regime '{current_regime}' during this "
                f"config's evidence period (regime_evidence={c.regime_evidence}).",
            ))
            continue
        considered.append(ConsideredCandidate(c.config_id, c.gate_status, f"Gate status: {c.gate_status}"))
        eligible.append(c)

    if not eligible:
        reason = (
            f"No researched strategy configuration exists for {instrument} {timeframe}."
            if not matching else
            f"All configurations for {instrument} {timeframe} were excluded (rejected, or "
            f"incompatible with the current regime '{current_regime}')."
        )
        return SelectionResult(
            instrument, timeframe, "NO_VALIDATED_EDGE", None, reason, tuple(considered),
            _research_recommendation_for("NO_VALIDATED_EDGE", matching),
        )

    best_rank = min(_GATE_RANK[c.gate_status] for c in eligible)
    best_tier = [c for c in eligible if _GATE_RANK[c.gate_status] == best_rank]
    best_tier.sort(key=lambda c: c.config_id)
    selected = best_tier[0]

    status = _STATUS_FOR_GATE[selected.gate_status]

    if status == "NO_VALIDATED_EDGE":
        reason = f"Every eligible configuration for {instrument} {timeframe} has gate status {selected.gate_status} (rejected)."
        selected_id = None
    else:
        reason = f"Selected {selected.config_id}: gate status {selected.gate_status} (statistical evidence: {selected.statistical_level})."
        selected_id = selected.config_id

    return SelectionResult(
        instrument, timeframe, status, selected_id, reason, tuple(considered),
        _research_recommendation_for(status, eligible),
    )
