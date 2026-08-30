"""
Interface for a future AI-generated research proposal — SCHEMA
VALIDATION ONLY. No LLM is connected here or anywhere in this phase.

SECURITY GUARANTEE: this module contains no dynamic code execution
of any kind — no shelling out to the operating system, no dynamic
import, and no getattr()-based
dynamic attribute access. parse_ai_proposal() only ever succeeds by
constructing real Condition/Hypothesis dataclass instances, whose own
__post_init__ validation (see hypothesis.py) rejects anything outside
the closed field/operator allowlist. A malformed or malicious proposal
— extra keys, code-like strings, unknown fields — is rejected with a
ValueError, never partially executed, never silently accepted.

FUTURE FLOW (not implemented yet — this module is preparation only):

    AI proposal (dict)
        -> parse_ai_proposal()          <- THIS module, exists now
        -> Hypothesis                   <- validated, JSON-safe only
        -> human/research review        <- not built yet
        -> register_hypothesis()        <- Phase 7, exists now
        -> run_research_experiment()    <- Phase 7, exists now

The AI never gets a code path to the backtester, the broker adapter,
or anything execution-related — it can only ever produce data that
either validates into a Hypothesis or is rejected outright.
"""

from app.research.hypothesis import (
    ALLOWED_CONDITION_FIELDS, ALLOWED_OPERATORS, Condition, Hypothesis, HypothesisType, RuleSet,
    new_hypothesis_id,
)

REQUIRED_PROPOSAL_KEYS = frozenset({
    "name", "description", "hypothesis_type", "market", "timeframe",
    "entry_long", "entry_short", "rationale",
})

# Keys that, if present, would indicate an attempt to smuggle something
# beyond a plain data proposal — rejected outright, not stripped/ignored.
FORBIDDEN_PROPOSAL_KEYS = frozenset({
    "code", "python", "expression", "eval", "exec", "script", "callable", "function", "sql", "query",
})


def _parse_ruleset(raw: list) -> RuleSet:
    if not isinstance(raw, list):
        raise ValueError("entry_long/entry_short must be a list of condition dicts.")
    conditions = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Each condition must be a dict, got {type(item)}.")
        extra_keys = set(item.keys()) - {"field", "operator", "value", "compare_field"}
        if extra_keys:
            raise ValueError(f"Condition contains unexpected keys: {extra_keys}")
        conditions.append(Condition(
            field=item.get("field"), operator=item.get("operator"),
            value=item.get("value"), compare_field=item.get("compare_field"),
        ))
    return RuleSet(conditions=tuple(conditions))


def parse_ai_proposal(proposal: dict) -> Hypothesis:
    """
    Validates a raw dict (as an AI system would eventually produce)
    into a real Hypothesis. Raises ValueError on anything that doesn't
    fit the closed schema — never executes, evaluates, or imports
    anything based on the proposal's content.
    """
    if not isinstance(proposal, dict):
        raise ValueError("AI proposal must be a dict.")

    forbidden_found = FORBIDDEN_PROPOSAL_KEYS & set(proposal.keys())
    if forbidden_found:
        raise ValueError(f"Proposal contains forbidden key(s): {forbidden_found}")

    missing = REQUIRED_PROPOSAL_KEYS - set(proposal.keys())
    if missing:
        raise ValueError(f"Proposal missing required key(s): {missing}")

    try:
        hypothesis_type = HypothesisType(proposal["hypothesis_type"])
    except ValueError:
        raise ValueError(
            f"Unknown hypothesis_type {proposal['hypothesis_type']!r}. "
            f"Allowed: {[t.value for t in HypothesisType]}"
        )

    entry_long = _parse_ruleset(proposal["entry_long"])
    entry_short = _parse_ruleset(proposal["entry_short"])

    name = proposal["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string.")

    return Hypothesis(
        id=new_hypothesis_id(name), name=name, description=str(proposal["description"]),
        hypothesis_type=hypothesis_type, market=str(proposal["market"]), timeframe=str(proposal["timeframe"]),
        entry_long=entry_long, entry_short=entry_short,
        risk_conditions=proposal.get("risk_conditions", {}) if isinstance(proposal.get("risk_conditions", {}), dict) else {},
        rationale=str(proposal["rationale"]),
        data_requirements=tuple(proposal.get("data_requirements", ())),
    )
