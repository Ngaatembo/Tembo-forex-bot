# Strategy Engine (Phase 3+)

Not yet implemented. This doc will define the common `Strategy`
interface and the four initial strategies once Phase 2 (technical
engine) is complete:

- **Trend following** — moving averages, momentum, ADX, volatility
- **Breakout** — consolidation detection, volatility expansion, confirmation
- **Mean reversion** — deviation from statistical mean, range conditions
- **News + technical** — economic/news event + surprise + AI interpretation
  + immediate price reaction + technical confirmation

No strategy is assumed profitable. Each must be independently
backtestable and validated out-of-sample before being considered for
paper trading (see `development-roadmap.md`, Phase 4 and Phase 20 of
the original spec — validation pipeline).
