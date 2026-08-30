"""
Research priority — a deterministic classification of where further
research EFFORT is justified. Explicitly NOT a profitability score.
"HIGH priority" means "an unresolved question here is worth answering,"
never "this will make money."

Reuses the Research Gate (research_gate.py) and Family Saturation
(family_saturation.py) directly — this module adds no new evidence
judgment of its own beyond combining what those two already decided.

WHY GATE STATUS ALONE ISN'T ENOUGH: ROBUSTNESS_REQUIRED is returned by
the gate for two very different underlying situations — a candidate
whose Verdict was PROMISING but got blocked on missing robustness
evidence (a genuinely live, positive-looking lead), and a candidate
whose Verdict was merely OVERFIT_SUSPECTED (an inconsistent, weaker
signal). Priority needs to tell these apart, which is why this
function also takes the candidate's EDGE score level (from
scorecard.py) as a separate input — this is exactly what implements
the project's own stated example: "a promising candidate with missing
robustness may have higher research priority than a fully rejected
family."
"""

from dataclasses import dataclass

from app.research.family_saturation import FamilySaturation


@dataclass(frozen=True)
class PriorityResult:
    priority: str  # "HIGH" | "MEDIUM" | "LOW" | "CLOSED"
    reason: str


def compute_research_priority(
    gate_status: str, edge_level: str, family_saturation: FamilySaturation,
) -> PriorityResult:
    if gate_status in ("REJECT_EARLY", "CLOSED"):
        return PriorityResult(
            "CLOSED",
            f"Research gate already classified this candidate as {gate_status} — "
            "no further research effort is justified on this specific line of inquiry.",
        )

    # A candidate that is individually still open (not gate-closed) but
    # sits inside an already-saturated family gets its priority pulled
    # down — UNLESS it's individually one of the strongest possible
    # results (PROMISING/PAPER_CANDIDATE), in which case a single real
    # positive lead should never be buried just because most of its
    # family failed.
    if family_saturation.saturation_status == "SATURATED" and gate_status not in ("PROMISING", "PAPER_CANDIDATE"):
        return PriorityResult(
            "LOW",
            f"Family has accumulated saturating negative evidence "
            f"({family_saturation.negative_evidence_density:.0%} negative across "
            f"{family_saturation.hypothesis_count} candidates) — further variations within "
            "this family have low research value, regardless of this candidate's individual state.",
        )

    if gate_status == "PAPER_CANDIDATE":
        return PriorityResult(
            "HIGH",
            "Gate status is PAPER_CANDIDATE — the strongest, most-resolved positive evidence "
            "this system produces. Worth continued research attention to confirm before any "
            "human paper-trading decision.",
        )

    if gate_status == "PROMISING":
        return PriorityResult(
            "HIGH",
            "Gate status is PROMISING — a consistently positive result across all periods that "
            "remains unresolved. This is exactly the kind of unresolved positive signal research "
            "effort should concentrate on.",
        )

    if gate_status == "ROBUSTNESS_REQUIRED":
        if edge_level == "STRONG":
            return PriorityResult(
                "HIGH",
                "Gate status is ROBUSTNESS_REQUIRED, but the underlying edge evidence is STRONG "
                "(a positive Verdict blocked only by missing/weak robustness or risk evidence) — "
                "this is a live, unresolved lead worth prioritizing, not a weak result.",
            )
        return PriorityResult(
            "MEDIUM",
            f"Gate status is ROBUSTNESS_REQUIRED with edge evidence only {edge_level} — an "
            "inconsistent or unproven signal that deserves resolution, but isn't yet a strong "
            "enough lead to prioritize over other open questions.",
        )

    if gate_status == "RESEARCH":
        return PriorityResult(
            "MEDIUM",
            "Gate status is RESEARCH (verdict INCONCLUSIVE) — insufficient evidence to judge "
            "either way. Worth investigating further, but not yet known to be a strong lead.",
        )

    return PriorityResult("MEDIUM", f"Unrecognized gate status {gate_status!r} — defaulting to MEDIUM conservatively.")
