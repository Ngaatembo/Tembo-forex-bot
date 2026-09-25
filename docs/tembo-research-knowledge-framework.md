# Tembo Research-to-Engine Framework

## Purpose
Tembo treats books, trader interviews, papers, and other research as **sources of hypotheses**, not as automatic trading rules.

A source can explain a market idea. Tembo must independently test that idea before it can influence a production decision.

## Evidence pipeline
Source -> Extracted claim/concept -> Explicit hypothesis -> Deterministic implementation -> Historical experiment -> Development / validation / out-of-sample evaluation -> Transaction-cost and slippage sensitivity -> Baseline comparison -> Overfitting diagnostics -> Statistical evidence -> Research Gate -> Production candidate only when the required evidence exists.

A failed or inconclusive experiment is a useful result. It must not be silently rewritten into a positive rule.

## Source classes
### Practitioner / book evidence
Use for:
- ideas worth testing
- definitions and qualitative context
- risk-management principles
- examples of how practitioners reasoned

Do not use for:
- claiming a rule is profitable merely because a successful trader used it
- assigning causal success to a book
- bypassing empirical validation

### Academic / quantitative evidence
Use for:
- prior empirical findings
- testable mechanisms
- statistical methods
- known failure modes

These sources still do not automatically authorize a Tembo rule. Tembo should reproduce or adapt the idea and test it on its own dataset.

### Market-data evidence
Use for:
- actual OHLC/market observations
- execution-cost assumptions
- regime and event context

The dataset, period, timezone, transformations, and cost assumptions must be recorded.

## Hypothesis record
Every book-derived idea that enters code should map to a structured Hypothesis containing:
- source_id
- source_location
- concept
- hypothesis_type
- market
- timeframe
- entry_long / entry_short
- exit/risk assumptions
- rationale
- data requirements
- version

The existing Hypothesis model is deliberately closed and JSON-safe. It does not permit executable expressions.

## Experiment requirements
A serious candidate should record:
- exact dataset version and hash
- evidence period
- development split
- validation split
- untouched out-of-sample split
- transaction-cost model
- slippage model
- risk configuration
- baseline comparison
- overfitting diagnostics
- statistical evidence where available
- reproducibility metadata

Tembo's existing ResearchExperiment already provides this structure.

## Research Gate
A hypothesis can move through:
RESEARCH -> ROBUSTNESS_REQUIRED -> PROMISING -> PAPER_CANDIDATE

or terminate as:
REJECT_EARLY / CLOSED

PAPER_CANDIDATE is **not execution permission**. It means the evidence has reached the project's defined research threshold and can be considered for a separate paper-trading stage.

## How books influence Tembo
Books should contribute to different layers:
1. **Signal hypotheses** — ideas about entries/exits.
2. **Context hypotheses** — trend, structure, volatility, regime.
3. **Risk constraints** — stop placement, position sizing, exposure and loss limits.
4. **Execution assumptions** — spread, slippage and practical fill constraints.
5. **Research methodology** — ways to avoid hindsight and overfitting.

Risk and execution lessons should not be forced into the signal engine.

## Candlestick rule
Candlestick patterns are evidence, not orders.

A pattern must be evaluated in context:
pattern + trend + structure + momentum + volatility + costs + regime

The detector must never look ahead. Confirmation-required patterns must only become confirmed after the confirming candle has actually closed.

Numerical thresholds that are not explicitly supplied by a source must be labelled as **Tembo operationalizations**, not attributed to the source.

## Anti-overfitting rules
Tembo must not:
- select a strategy because it has the highest historical profit factor
- repeatedly tune parameters against the same out-of-sample period
- treat a high win rate as sufficient evidence
- ignore transaction costs
- turn an inconclusive result into a positive result
- allow AI-generated text or code to bypass the structured hypothesis/evaluation layer
- fabricate live prices or research statistics

## Promotion rule
Only research artifacts with traceable evidence may become inputs to the decision engine.

The decision engine should consume validated configuration snapshots and current verified market observations, not raw book text.

## Current implementation status
Already implemented:
- structured hypotheses
- deterministic rule evaluation
- experiment records
- development/validation/out-of-sample splits
- baseline comparison
- overfitting diagnostics
- research scorecard
- research gate
- validated strategy configuration
- strategy selector
- book-derived candlestick evidence
- candlestick historical research with cost sensitivity

Next research work:
1. register the specific book/source claims we want to test;
2. map each claim to a hypothesis ID;
3. run reproducible experiments;
4. promote only evidence-supported configurations;
5. only then connect them to the multi-factor decision engine.