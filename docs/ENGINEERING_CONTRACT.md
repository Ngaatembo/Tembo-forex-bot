# Tembo Engineering Contract

## Production boundary
Tembo is a market-research and paper-trading platform until a real broker adapter is implemented and verified.

The intended boundary is:

**market data → analysis → strategy → risk → paper execution → live execution**

AI cannot bypass the risk engine.

## Data integrity
A quote or candle may be shown as live only after provider retrieval, normalization and validation. Mock data must never be presented as verified live market data.

The cockpit supports M5, M15, H1, H4 and D1. Synthetic instruments must be discovered/validated through the Deriv provider before use.

## Execution safety
Live execution requires:
1. explicit ENABLE_LIVE_EXECUTION=true;
2. a registered real broker adapter;
3. passing risk evaluation;
4. validated order parameters;
5. end-to-end demo-account tests for the selected broker.

If any requirement is missing or unknown, the system must fail closed.

## Research integrity
Backtests must not use future information. Strategies must be independently measurable, and research results must remain distinguishable from live-market observations.

## Completion definition
A feature is complete only when it is implemented, integrated into the production path, covered by regression tests, and its failure mode is explicit.

A UI control alone is not evidence that an integration exists.

## Live-trading gate
Until a real broker adapter exists, the correct production state is:

**LIVE EXECUTION BLOCKED.**

This is intentional and must not be weakened to make the UI appear complete.
