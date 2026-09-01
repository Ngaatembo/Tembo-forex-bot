"""
PaperTradingEngine — the authoritative decision chain for paper
trading. No component may bypass an earlier safety layer; each stage
below is a separate early-return, same discipline as
app.risk_engine.risk_engine.evaluate_risk()'s own hierarchy.

    1. Instrument/timeframe validation
    2. Strategy selection (Phase 14 Selector)
    3. Research Gate (encoded in the Selector's own status)
    4. Macro/Event Safety Gate (Step 4, news_engine) — OPTIONAL,
       caller-supplied. A HIGH MacroEventRisk blocks the trade here,
       before Risk Engine ever runs. This layer can only ever
       RESTRICT — it has no path to approve a trade on its own; a
       missing/None macro_event_risk simply skips this stage
       (backward compatible with every existing caller/test).
    5. Signal/stop validation (delegated to Risk Engine, stage 6)
    6. Risk Engine (Phase 15) — includes the kill switch as ITS first stage
    7. Paper execution

SECURITY: this module has no import of, and no code path to, the
execution/broker layer. A PAPER_TRADE_APPROVED decision opens a
PaperPosition — a data object — never places anything with a real
broker.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.news_engine.models import MACRO_RISK_HIGH, MacroEventRisk
from app.paper_trading.account import PaperAccountState
from app.paper_trading.models import PaperPosition, PaperTrade
from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.risk_engine.risk_engine import evaluate_risk
from app.risk_engine.risk_models import RiskLimitsConfig

_VALID_TIMEFRAMES = {"m5", "m15", "h1", "h4", "d1"}

DECISION_STATES = frozenset({
    "INVALID_INPUT", "NO_VALIDATED_EDGE", "PROMISING_NOT_TRADEABLE", "RESEARCH_REQUIRED",
    "MACRO_EVENT_RISK_BLOCKED", "RISK_REJECTED", "KILL_SWITCH_BLOCKED", "PAPER_TRADE_APPROVED",
})


@dataclass(frozen=True)
class PaperTradeDecision:
    status: str
    reason: str
    position: Optional[PaperPosition] = None

    def __post_init__(self):
        if self.status not in DECISION_STATES:
            raise ValueError(f"Unknown decision state {self.status!r}.")


def _check_paper_exit(position: PaperPosition, current_price: float) -> Optional[str]:
    if position.stop_price is not None:
        if position.direction == "LONG" and current_price <= position.stop_price:
            return "STOP_LOSS"
        if position.direction == "SHORT" and current_price >= position.stop_price:
            return "STOP_LOSS"
    if position.take_profit_price is not None:
        if position.direction == "LONG" and current_price >= position.take_profit_price:
            return "TAKE_PROFIT"
        if position.direction == "SHORT" and current_price <= position.take_profit_price:
            return "TAKE_PROFIT"
    if position.max_holding_periods is not None and position.periods_held >= position.max_holding_periods:
        return "MAX_HOLDING_PERIOD"
    return None


class PaperTradingEngine:
    def __init__(self, account: PaperAccountState, configs: list[ValidatedStrategyConfig], risk_limits: RiskLimitsConfig):
        self.account = account
        self.configs = configs
        self.risk_limits = risk_limits
        self._position_counter = 0

    def evaluate_and_maybe_open(
        self, *, instrument: str, timeframe: str, direction: str, entry_price: float,
        stop_price: Optional[float], current_prices: dict, take_profit_price: Optional[float] = None,
        max_holding_periods: Optional[int] = None, current_regime: Optional[str] = None,
        macro_event_risk: Optional[MacroEventRisk] = None,
    ) -> PaperTradeDecision:
        if not instrument or not timeframe:
            return PaperTradeDecision("INVALID_INPUT", "instrument and timeframe are both required.")
        timeframe_norm = timeframe.lower()
        if timeframe_norm not in _VALID_TIMEFRAMES:
            return PaperTradeDecision("INVALID_INPUT", f"Invalid timeframe {timeframe!r}. Must be one of {sorted(_VALID_TIMEFRAMES)}.")

        selection = select_strategy(instrument, timeframe_norm, self.configs, current_regime)
        if selection.status == "NO_VALIDATED_EDGE":
            return PaperTradeDecision("NO_VALIDATED_EDGE", selection.reason)
        if selection.status == "PROMISING_NOT_TRADEABLE":
            return PaperTradeDecision("PROMISING_NOT_TRADEABLE", selection.reason)
        if selection.status == "RESEARCH_REQUIRED":
            return PaperTradeDecision("RESEARCH_REQUIRED", selection.reason)

        # Macro/Event Safety Gate — sits between Research Gate and Risk
        # Engine. Can only RESTRICT (block on HIGH risk); a None value
        # or non-HIGH level simply passes through to Risk Engine as
        # before. News/macro data can never independently approve a trade.
        if macro_event_risk is not None and macro_event_risk.level == MACRO_RISK_HIGH:
            return PaperTradeDecision("MACRO_EVENT_RISK_BLOCKED", macro_event_risk.reason)

        key = f"{instrument}:{timeframe_norm}"
        if key in self.account.open_positions:
            risk_decision = None
            risk_reason = f"A position is already open for {key} — duplicate positions are not permitted."
        else:
            snapshot_prices = dict(current_prices)
            snapshot_prices.setdefault(key, entry_price)
            account_snapshot = self.account.to_risk_engine_snapshot(snapshot_prices)
            instrument_info = InstrumentTimeframeInfo(instrument, timeframe_norm, mean_price=entry_price, price_precision_decimals=5)
            risk_decision = evaluate_risk(
                selection_result=selection, account=account_snapshot, limits=self.risk_limits,
                direction=direction, entry_price=entry_price, stop_price=stop_price, instrument_info=instrument_info,
            )
            risk_reason = risk_decision.reason

        if risk_decision is None:
            return PaperTradeDecision("RISK_REJECTED", risk_reason)
        if risk_decision.state == "KILL_SWITCH_ACTIVE":
            return PaperTradeDecision("KILL_SWITCH_BLOCKED", risk_reason)
        if risk_decision.state != "APPROVED":
            return PaperTradeDecision("RISK_REJECTED", risk_reason)

        self._position_counter += 1
        position = PaperPosition(
            position_id=f"paper_pos_{self._position_counter}", instrument=instrument, timeframe=timeframe_norm,
            direction=direction, entry_price=entry_price, entry_time=datetime.now(), stop_price=stop_price,
            position_size=risk_decision.position_sizing.final_position_size, candidate_config_id=selection.selected_config_id,
            take_profit_price=take_profit_price, max_holding_periods=max_holding_periods,
        )
        risk_amount = risk_decision.position_sizing.final_position_size * risk_decision.position_sizing.stop_distance
        self.account.open_position(position, risk_amount=risk_amount)
        return PaperTradeDecision("PAPER_TRADE_APPROVED", risk_decision.reason, position=position)

    def tick(self, current_prices: dict, current_time: datetime) -> list[PaperTrade]:
        closed_trades = []
        for key in list(self.account.open_positions.keys()):
            price = current_prices.get(key)
            if price is None:
                continue
            position = self.account.open_positions[key]
            position.periods_held += 1
            reason = _check_paper_exit(position, price)
            if reason:
                trade = self.account.close_position(key, exit_price=price, exit_time=current_time, exit_reason=reason)
                closed_trades.append(trade)
        return closed_trades
