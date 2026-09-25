# Tembo candlestick-book integration

Tembo uses the two uploaded candlestick documents as a source of pattern
definitions and pattern context, not as a claim that any pattern guarantees
profit.

## Source-derived rules

The books consistently emphasize that a candle's meaning depends on prior
market context. A hammer is the long-lower-shadow/small-body shape in a
downtrend; the same geometry in an uptrend is a Hanging Man. Engulfing
patterns are defined around a prior definable trend and the current real
body engulfing the prior real body. Morning/Evening Star structures use
three candles and reversal context.

The larger 21 Candlesticks document also repeatedly calls for confirmation
after reversal patterns. Tembo therefore exposes confirmation_required and
confirmed instead of treating detection as an order.

## Explicit Tembo operationalizations

The books use qualitative terms such as "very small", "definite trend", and
"continued buying/selling". The code must turn those into numbers without
pretending the source supplied them:

- Doji: body <= 10% of candle range.
- Trend context: last 10 completed closes, at least half directional and at
  least 0.2% net movement.
- Hammer/Hanging Man/Shooting Star/Inverted Hammer confirmation: next
  completed candle closes in the expected direction.
- Dark Cloud Cover and Piercing use the source's strict gap form. We do not
  silently replace the gap requirement with a looser forex-specific rule.

These are engineering hypotheses, not facts from the books. They must be
validated out-of-sample before entering the live decision engine.

## How Tembo will test whether the book information has edge

The research experiment is deliberately separated from live execution:

1. Detect patterns using candles available at that moment only.
2. Enter no earlier than the next available candle.
3. Measure forward returns at multiple horizons.
4. Split history chronologically into train / validation / out-of-sample.
5. Report occurrence count, directional hit rate, average forward return,
   median return and adverse/favorable excursion.
6. Compare patterns with and without context/confirmation.
7. Do not tune thresholds on the out-of-sample period.

A positive historical result is evidence to investigate further, not proof of
future profitability.


## Research gate update

The empirical study now treats transaction-cost sensitivity and out-of-sample persistence as mandatory evidence before a book-derived hypothesis can be considered for further research. Cost values are sensitivity assumptions, not broker-specific quotes.
