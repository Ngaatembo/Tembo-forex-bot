"""
Research Gate — converts an existing Verdict + Scorecard + overfitting
diagnostics into a research-STAGE classification. Does not replace or
recompute Verdict (verdict.py, untouched) — it wraps it.

REJECT_EARLY vs CLOSED, the one non-obvious distinction here:
  - REJECT_EARLY: Verdict is REJECTED — the hypothesis failed at the
    cheapest, earliest check (development itself never worked). Little
    research was invested before this conclusion.
  - CLOSED: Verdict is OUT_OF_SAMPLE_FAILED — the FULL evaluation
    pipeline ran (development, validation, AND out-of-sample, plus
    baseline comparison) and it still failed. More evidence was
    gathered before reaching a negative conclusion, so this is
    "closed after full evaluation," not "rejected on sight."
  Both are terminal/negative — the label only reflects how much
  evidence was actually gathered before the negative conclusion.

PAPER_CANDIDATE is deliberately a HIGH bar — requires STRONG robustness
AND STRONG statistical evidence AND risk/realism at least MODERATE,
with zero overfitting flags. It does not mean "start paper trading" —
see docs; nothing in this module can execute anything regardless of
gate status.
"""

from dataclasses import asdict, dataclass

from app.research.overfitting import OverfittingDiagnostics
from app.research.scorecard import Scorecard
from app.research.verdict import Verdict

GATE_STATES = (
    "REJECT_EARLY", "RESEARCH", "ROBUSTNESS_REQUIRED", "PROMISING", "PAPER_CANDIDATE", "CLOSED",
)


@dataclass(frozen=True)
class GateResult:
    status: str
    reason: str
    evidence_used: dict  # small, traceable snapshot of what went into the decision

    def to_dict(self) -> dict:
        return asdict(self)


def _evidence_snapshot(verdict: Verdict, scorecard: Scorecard, overfitting: OverfittingDiagnostics) -> dict:
    return {
        "verdict": verdict.value,
        "overfitting_any_flag_raised": overfitting.any_flag_raised,
        "edge_level": scorecard.edge.level,
        "robustness_level": scorecard.robustness.level,
        "risk_level": scorecard.risk.level,
        "statistical_level": scorecard.statistical.level,
        "realism_level": scorecard.realism.level,
    }


def compute_research_gate(
    verdict: Verdict, scorecard: Scorecard, overfitting: OverfittingDiagnostics
) -> GateResult:
    evidence = _evidence_snapshot(verdict, scorecard, overfitting)

    if verdict == Verdict.REJECTED:
        return GateResult(
            "REJECT_EARLY",
            "Verdict is REJECTED — development itself showed no edge (profit_factor <= 1.0). "
            "No further research effort is justified here.",
            evidence,
        )

    if verdict == Verdict.OUT_OF_SAMPLE_FAILED:
        return GateResult(
            "CLOSED",
            "Verdict is OUT_OF_SAMPLE_FAILED — the full development/validation/out-of-sample "
            "evaluation ran and out-of-sample did not confirm the development-period edge. "
            "A strong development result alone can never override this.",
            evidence,
        )

    if verdict == Verdict.INCONCLUSIVE:
        return GateResult(
            "RESEARCH",
            "Verdict is INCONCLUSIVE — insufficient trade count in at least one period to judge "
            "either way. This still deserves investigation, not rejection.",
            evidence,
        )

    # From here: verdict is PROMISING, OVERFIT_SUSPECTED, or (defensively)
    # VALIDATED_FOR_PAPER_TRADING — some positive edge signal exists.
    # VALIDATED_FOR_PAPER_TRADING is never auto-assigned by compute_verdict(),
    # but is handled here defensively and identically to PROMISING — this
    # gate NEVER treats any verdict as trading permission; it only
    # classifies research stage.

    if overfitting.any_flag_raised:
        return GateResult(
            "ROBUSTNESS_REQUIRED",
            "Overfitting diagnostics raised at least one flag — this blocks any further "
            "advancement regardless of what the verdict says.",
            evidence,
        )

    if verdict == Verdict.OVERFIT_SUSPECTED:
        return GateResult(
            "ROBUSTNESS_REQUIRED",
            "Verdict is OVERFIT_SUSPECTED — an edge appears in some periods but not "
            "consistently. More robustness evidence is required before this can advance.",
            evidence,
        )

    if scorecard.robustness.level in ("WEAK", "UNKNOWN"):
        return GateResult(
            "ROBUSTNESS_REQUIRED",
            f"Robustness evidence is {scorecard.robustness.level} despite a positive verdict — "
            f"{scorecard.robustness.reason}",
            evidence,
        )

    if scorecard.risk.level == "WEAK":
        return GateResult(
            "ROBUSTNESS_REQUIRED",
            f"Risk profile is WEAK ({scorecard.risk.reason}) — a high win rate alone cannot "
            "bypass a poor payoff ratio or excessive drawdown.",
            evidence,
        )

    paper_candidate_ready = (
        scorecard.robustness.level == "STRONG"
        and scorecard.risk.level in ("STRONG", "MODERATE")
        and scorecard.statistical.level == "STRONG"
        and scorecard.realism.level in ("STRONG", "MODERATE")
    )

    if paper_candidate_ready:
        return GateResult(
            "PAPER_CANDIDATE",
            "Robustness and statistical evidence are both STRONG, risk and realism are at "
            "least MODERATE, and no overfitting flags were raised. This means a human MAY "
            "reasonably consider advancing this candidate to a dedicated paper-trading "
            "decision — it does NOT start paper trading and does NOT authorize any execution.",
            evidence,
        )

    return GateResult(
        "PROMISING",
        "Verdict is positive and robustness/risk are not weak, but statistical and/or realism "
        "evidence isn't yet strong enough to justify PAPER_CANDIDATE status. Worth continued "
        "research, not yet worth a paper-trading discussion.",
        evidence,
    )
