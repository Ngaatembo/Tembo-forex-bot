"""
Convenience entrypoints for deterministic strategy evaluation.

This module receives already-validated candles and a researched strategy
configuration. It never fetches data, touches accounts, or places orders.
The live evaluator exists so the strategy selected by the research gate is
actually run against the same completed candles shown by the cockpit.
"""

from dataclasses import dataclass
import re

from app.data_engine.market_data import Candle
from app.research.hypothesis import HypothesisType
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.crossover import detect_crossover_signals
from app.strategy_engine.momentum import detect_momentum_signals
from app.strategy_engine.models import Signal
from app.technical_engine.service import calculate_features


@dataclass(frozen=True)
class LiveStrategyResult:
    config_id: str
    strategy_family: str
    status: str
    direction: str
    triggered: bool
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    reason: str
    parameter_summary: dict


def run_crossover_strategy(candles: list[Candle], symbol: str) -> list[Signal]:
    features = calculate_features(candles)
    return detect_crossover_signals(features, symbol=symbol)


def _candidate_number(
    config: ValidatedStrategyConfig,
    key: str,
    default: int,
) -> int:
    value = config.parameters.get(key)
    if value is not None:
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except (TypeError, ValueError):
            pass

    # Older research snapshots stored some parameters only in candidate_id.
    match = re.search(rf"{re.escape(key)}[_-]?(\\d+)", config.candidate_id.lower())
    return int(match.group(1)) if match else default


def _signal_for_config(
    candles: list[Candle],
    symbol: str,
    config: ValidatedStrategyConfig,
) -> tuple[Signal | None, dict]:
    family = config.strategy_family

    if family == HypothesisType.BREAKOUT:
        lookback = _candidate_number(config, "lookback", 20)
        signals = detect_breakout_signals(candles, lookback, symbol)
        return signals[-1] if signals else None, {"lookback": lookback}

    if family == HypothesisType.MOMENTUM:
        lookback = _candidate_number(config, "lookback", 20)
        signals = detect_momentum_signals(candles, lookback, symbol)
        return signals[-1] if signals else None, {"lookback": lookback}

    if family in {HypothesisType.TREND_FOLLOWING}:
        signals = run_crossover_strategy(candles, symbol)
        return signals[-1] if signals else None, {"method": "SMA10/SMA50 crossover"}

    return None, {}


def evaluate_live_strategy(
    candles: list[Candle],
    symbol: str,
    config: ValidatedStrategyConfig,
    atr: float | None = None,
) -> LiveStrategyResult:
    """
    Run the selected researched strategy on the latest completed candle.

    The research gate remains authoritative: this function reports what the
    strategy says, but it does not decide whether that signal is tradeable.
    """
    if len(candles) < 2:
        return LiveStrategyResult(
            config.config_id,
            config.strategy_family.value,
            "INSUFFICIENT_DATA",
            "WAIT",
            False,
            None,
            None,
            None,
            None,
            "Not enough completed candles to evaluate the selected strategy.",
            {},
        )

    signal, parameters = _signal_for_config(candles, symbol, config)

    if signal is None:
        return LiveStrategyResult(
            config.config_id,
            config.strategy_family.value,
            "NOT_IMPLEMENTED",
            "WAIT",
            False,
            None,
            None,
            None,
            None,
            f"Strategy family {config.strategy_family.value!r} is not implemented in the live evaluator.",
            parameters,
        )

    direction = signal.direction
    if direction not in {"BUY", "SELL"}:
        return LiveStrategyResult(
            config.config_id,
            config.strategy_family.value,
            "WAITING",
            direction,
            False,
            None,
            None,
            None,
            None,
            signal.reason,
            parameters,
        )

    entry = float(candles[-1].close)
    atr_multiple = config.exit_config_summary.get("atr_stop_multiple")
    if atr is None or atr <= 0 or atr_multiple is None:
        return LiveStrategyResult(
            config.config_id,
            config.strategy_family.value,
            "SIGNAL_NO_EXIT",
            direction,
            True,
            entry,
            None,
            None,
            None,
            "Strategy triggered, but its researched ATR exit configuration or live ATR is unavailable.",
            parameters,
        )

    try:
        distance = float(atr) * float(atr_multiple)
    except (TypeError, ValueError):
        return LiveStrategyResult(
            config.config_id,
            config.strategy_family.value,
            "SIGNAL_NO_EXIT",
            direction,
            True,
            entry,
            None,
            None,
            None,
            "Strategy triggered, but its ATR exit configuration is invalid.",
            parameters,
        )

    if distance <= 0:
        return LiveStrategyResult(
            config.config_id,
            config.strategy_family.value,
            "SIGNAL_NO_EXIT",
            direction,
            True,
            entry,
            None,
            None,
            None,
            "Strategy triggered, but the calculated stop distance is invalid.",
            parameters,
        )

    if direction == "BUY":
        stop_loss = entry - distance
        take_profit = entry + distance * 2.0
    else:
        stop_loss = entry + distance
        take_profit = entry - distance * 2.0

    return LiveStrategyResult(
        config.config_id,
        config.strategy_family.value,
        "TRIGGERED",
        direction,
        True,
        entry,
        stop_loss,
        take_profit,
        2.0,
        signal.reason,
        parameters,
    )
