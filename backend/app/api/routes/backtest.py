"""
POST /backtests/sma-crossover

Runs the SMA10/50 crossover strategy through the backtesting engine
against stored historical candles and returns the full result.

This endpoint ONLY simulates. It has no import of, and no code path
to, the live/paper execution layer — nothing here can place a real or
paper order. See tests/test_backtest_security_boundary.py, which
verifies this at the source-code level, not just by convention.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest
from app.data_engine.market_data import Candle
from app.database.models import MarketCandle
from app.database.session import AsyncSessionLocal


router = APIRouter(prefix="/backtests", tags=["backtesting"])


@router.get("/readiness")
async def backtest_readiness() -> dict:
    """Report whether stored historical candles are available for simulation."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                MarketCandle.symbol,
                MarketCandle.timeframe,
                func.count(MarketCandle.id).label("candle_count"),
                func.min(MarketCandle.timestamp).label("first_candle"),
                func.max(MarketCandle.timestamp).label("last_candle"),
            )
            .group_by(MarketCandle.symbol, MarketCandle.timeframe)
            .order_by(MarketCandle.symbol, MarketCandle.timeframe)
        )
        rows = result.all()

    datasets = [
        {
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "candle_count": int(row.candle_count),
            "first_candle": row.first_candle.isoformat() if row.first_candle else None,
            "last_candle": row.last_candle.isoformat() if row.last_candle else None,
        }
        for row in rows
    ]
    return {
        "ready": bool(datasets),
        "stored_candles": sum(item["candle_count"] for item in datasets),
        "datasets": datasets,
        "note": (
            "Backtests use validated historical candles stored in PostgreSQL. "
            "Live provider reads do not automatically imply historical backtest data is stored."
        ),
    }


@router.get("/baseline")
async def baseline_backtest(
    symbol: str = "EUR/USD",
    timeframe: str = "h1",
) -> dict:
    """Run the frozen baseline against all stored candles and return a compact report."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MarketCandle)
            .where(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
            .order_by(MarketCandle.timestamp.asc())
        )
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No stored candles for {symbol} h1")

    candles = [
        Candle(
            symbol=r.symbol, timeframe=r.timeframe, timestamp=r.timestamp,
            open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume,
        )
        for r in rows
    ]
    config = BacktestConfig(
        symbol=symbol, timeframe="h1",
        initial_balance=10_000.0, position_size=10_000.0,
        spread=0.00010, slippage=0.00002,
    )
    result = run_backtest(candles, config)
    return {
        "status": "completed",
        "dataset": {
            "symbol": symbol, "timeframe": "h1", "candle_count": len(candles),
            "first_candle": candles[0].timestamp.isoformat(),
            "last_candle": candles[-1].timestamp.isoformat(),
        },
        "configuration": {
            "initial_balance": config.initial_balance, "position_size": config.position_size,
            "spread": config.spread, "slippage": config.slippage,
            "execution_model": config.execution_model,
        },
        "summary": {
            "initial_balance": result.summary.initial_balance,
            "final_balance": result.summary.final_balance,
            "net_pnl": result.summary.net_pnl,
            "total_return": result.summary.total_return,
            "trade_count": result.summary.trade_count,
            "winning_trades": result.summary.winning_trades,
            "losing_trades": result.summary.losing_trades,
            "win_rate": result.summary.win_rate,
            "average_win": result.summary.average_win,
            "average_loss": result.summary.average_loss,
            "expectancy": result.summary.expectancy,
            "profit_factor": result.summary.profit_factor,
            "max_drawdown": result.summary.max_drawdown,
            "max_drawdown_percent": result.summary.max_drawdown_percent,
        },
    }


@router.get("/walk-forward")
async def walk_forward_backtest(
    symbol: str = "EUR/USD",
    development_days: int = 720,
    validation_days: int = 180,
    out_of_sample_days: int = 180,
    step_days: int = 180,
) -> dict:
    """
    Run the frozen SMA10/50 crossover through rolling out-of-sample windows
    using the validated H1 historical candles already stored in PostgreSQL.

    This is research-only. It does not optimize parameters, select a winner,
    or place orders. Each window's OOS period is evaluated only after the
    development/validation history preceding it.
    """
    from app.research.periods import split_candles_by_period
    from app.research.walk_forward import (
        WalkForwardConfig,
        generate_walk_forward_windows,
    )

    if min(development_days, validation_days, out_of_sample_days, step_days) <= 0:
        raise HTTPException(status_code=400, detail="All walk-forward periods must be positive.")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MarketCandle)
            .where(
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == "h1",
            )
            .order_by(MarketCandle.timestamp.asc())
        )
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No stored candles for {symbol} h1")

    candles = [
        Candle(
            symbol=r.symbol, timeframe=r.timeframe, timestamp=r.timestamp,
            open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume,
        )
        for r in rows
    ]

    config = WalkForwardConfig(
        development_days=development_days,
        validation_days=validation_days,
        out_of_sample_days=out_of_sample_days,
        step_days=step_days,
    )
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(
        symbol=symbol,
        timeframe=timeframe,
        initial_balance=10_000.0,
        position_size=10_000.0,
        spread=0.00010,
        slippage=0.00002,
    )

    window_reports = []
    all_oos_trades = 0
    all_wins = 0
    all_net_pnl = 0.0
    worst_drawdown = 0.0

    for window in windows:
        split = split_candles_by_period(candles, window.periods)
        oos_candles = split["out_of_sample"]
        result = run_backtest(oos_candles, bt_config)
        summary = result.summary

        all_oos_trades += summary.trade_count
        all_wins += summary.winning_trades or 0
        all_net_pnl += summary.net_pnl
        worst_drawdown = max(worst_drawdown, summary.max_drawdown or 0.0)

        window_reports.append({
            "window": window.index,
            "oos_start": window.periods.out_of_sample.start.isoformat(),
            "oos_end": window.periods.out_of_sample.end.isoformat(),
            "oos_candles": len(oos_candles),
            "trade_count": summary.trade_count,
            "win_rate": summary.win_rate,
            "profit_factor": summary.profit_factor,
            "net_pnl": summary.net_pnl,
            "max_drawdown": summary.max_drawdown,
        })

    return {
        "status": "completed",
        "method": "rolling_out_of_sample",
        "strategy": "SMA10/SMA50 crossover",
        "dataset": {
            "symbol": symbol,
            "timeframe": timeframe,
            "candle_count": len(candles),
            "first_candle": candles[0].timestamp.isoformat(),
            "last_candle": candles[-1].timestamp.isoformat(),
        },
        "windows": {
            "development_days": development_days,
            "validation_days": validation_days,
            "out_of_sample_days": out_of_sample_days,
            "step_days": step_days,
            "count": len(windows),
        },
        "cost_model": {
            "spread": bt_config.spread,
            "slippage": bt_config.slippage,
            "execution_model": bt_config.execution_model,
        },
        "aggregate_oos": {
            "trade_count": all_oos_trades,
            "win_rate": (all_wins / all_oos_trades) if all_oos_trades else None,
            "net_pnl": all_net_pnl,
            "worst_window_drawdown": worst_drawdown,
        },
        "windows_report": window_reports,
        "note": (
            "Historical out-of-sample results are descriptive evidence, not "
            "a guarantee of future performance. No parameter optimization is "
            "performed by this endpoint."
        ),
    }


@router.get("/candidate-walk-forward")
async def candidate_walk_forward(
    symbol: str = "EUR/USD",
    development_days: int = 360,
    validation_days: int = 90,
    out_of_sample_days: int = 90,
    step_days: int = 90,
) -> dict:
    """Evaluate the existing frozen strategy candidates on rolling H1 OOS windows.

    No candidate is selected or optimized here. Each strategy is evaluated independently
    on the same OOS windows so the report can be compared without changing the research
    rules. Position sizing is instrument-aware, especially for XAU/USD.
    """
    from app.backtesting.engine_research import simulate_trades_with_exit_rules
    from app.backtesting.exit_rules import ExitConfig
    from app.strategy_engine.breakout import detect_breakout_signals
    from app.strategy_engine.momentum import detect_momentum_signals
    from app.strategy_engine.regime_filter import filter_signals_by_regime
    from app.technical_engine.features import calculate_feature_snapshots

    if min(development_days, validation_days, out_of_sample_days, step_days) <= 0:
        raise HTTPException(status_code=400, detail="All walk-forward periods must be positive.")

    position_sizes = {"EUR/USD": 10_000.0, "GBP/USD": 10_000.0, "XAU/USD": 8.298216860650118}
    if symbol not in position_sizes:
        raise HTTPException(status_code=400, detail=f"Unsupported symbol: {symbol}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MarketCandle)
            .where(MarketCandle.symbol == symbol, MarketCandle.timeframe == "h1")
            .order_by(MarketCandle.timestamp.asc())
        )
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No stored candles for {symbol} h1")

    candles = [Candle(symbol=r.symbol, timeframe=r.timeframe, timestamp=r.timestamp,
                       open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
                for r in rows]

    from app.research.periods import split_candles_by_period
    from app.research.walk_forward import WalkForwardConfig, generate_walk_forward_windows

    wf = WalkForwardConfig(development_days=development_days, validation_days=validation_days,
                           out_of_sample_days=out_of_sample_days, step_days=step_days)
    windows = generate_walk_forward_windows(candles, wf)
    features = calculate_feature_snapshots(candles)
    exit_config = ExitConfig(label="atr_2x_max100", atr_stop_multiple=2.0, max_holding_candles=100)
    candidates = {
        "breakout_30": ("breakout", 30),
        "breakout_40": ("breakout", 40),
        "breakout_50": ("breakout", 50),
        "momentum_20": ("momentum", 20),
        "regime_filtered_breakout_40": ("regime_breakout", 40),
    }
    bt_config = BacktestConfig(symbol=symbol, timeframe="h1", initial_balance=10_000.0,
                               position_size=position_sizes[symbol], spread=0.00010, slippage=0.00002)

    reports = {}
    for name, (kind, lookback) in candidates.items():
        windows_report = []
        total_trades = total_wins = 0
        total_pnl = 0.0
        for window in windows:
            split = split_candles_by_period(candles, window.periods)
            oos = split["out_of_sample"]
            if kind == "momentum":
                signals = detect_momentum_signals(oos, lookback=lookback, symbol=symbol)
                oos_features = calculate_feature_snapshots(oos)
            else:
                signals = detect_breakout_signals(oos, lookback=lookback, symbol=symbol)
                oos_features = calculate_feature_snapshots(oos)
                if kind == "regime_breakout":
                    signals = filter_signals_by_regime(signals, oos_features,
                                                       {"HIGH_VOLATILITY", "TRENDING_DOWN", "TRENDING_UP"})
            result = simulate_trades_with_exit_rules(oos, signals, oos_features, bt_config, exit_config)
            s = result.summary
            total_trades += s.trade_count
            total_wins += s.winning_trades or 0
            total_pnl += s.net_pnl
            windows_report.append({
                "window": window.index,
                "oos_start": window.periods.out_of_sample.start.isoformat(),
                "oos_end": window.periods.out_of_sample.end.isoformat(),
                "trade_count": s.trade_count,
                "win_rate": s.win_rate,
                "profit_factor": s.profit_factor,
                "net_pnl": s.net_pnl,
                "max_drawdown": s.max_drawdown,
            })
        reports[name] = {
            "aggregate_oos": {
                "trade_count": total_trades,
                "win_rate": (total_wins / total_trades) if total_trades else None,
                "net_pnl": total_pnl,
                "positive_windows": sum(1 for w in windows_report if (w["net_pnl"] or 0) > 0),
                "negative_windows": sum(1 for w in windows_report if (w["net_pnl"] or 0) < 0),
            },
            "windows_report": windows_report,
        }

    return {
        "status": "completed",
        "method": "independent_rolling_out_of_sample",
        "strategy_selection": "none — all candidates evaluated independently",
        "dataset": {"symbol": symbol, "timeframe": "h1", "candle_count": len(candles),
                    "first_candle": candles[0].timestamp.isoformat(),
                    "last_candle": candles[-1].timestamp.isoformat()},
        "windows": {"development_days": development_days, "validation_days": validation_days,
                    "out_of_sample_days": out_of_sample_days, "step_days": step_days, "count": len(windows)},
        "cost_model": {"spread": bt_config.spread, "slippage": bt_config.slippage,
                       "position_size": bt_config.position_size, "execution_model": bt_config.execution_model},
        "strategies": reports,
        "note": "Historical OOS evidence only; no parameter optimization and no execution path.",
    }



class BacktestRequest(BaseModel):
    symbol: str = "EUR/USD"
    timeframe: str = "h1"
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    initial_balance: float = Field(default=1000.0, gt=0)
    position_size: float = Field(default=10_000.0, gt=0)
    spread: float = Field(default=0.00010, ge=0)
    slippage: float = Field(default=0.0, ge=0)


@router.post("/sma-crossover")
async def backtest_sma_crossover(request: BacktestRequest) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(MarketCandle)
            .where(MarketCandle.symbol == request.symbol, MarketCandle.timeframe == request.timeframe)
            .order_by(MarketCandle.timestamp.asc())
        )
        if request.start is not None:
            stmt = stmt.where(MarketCandle.timestamp >= request.start)
        if request.end is not None:
            stmt = stmt.where(MarketCandle.timestamp <= request.end)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404, detail=f"No stored candles for {request.symbol} {request.timeframe}"
        )

    candles = [
        Candle(
            symbol=r.symbol, timeframe=r.timeframe, timestamp=r.timestamp,
            open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume,
        )
        for r in rows
    ]

    config = BacktestConfig(
        symbol=request.symbol, timeframe=request.timeframe,
        initial_balance=request.initial_balance, position_size=request.position_size,
        spread=request.spread, slippage=request.slippage,
    )

    backtest_result = run_backtest(candles, config)

    return {
        "configuration": {
            "symbol": config.symbol, "timeframe": config.timeframe,
            "initial_balance": config.initial_balance, "position_size": config.position_size,
            "spread": config.spread, "slippage": config.slippage,
            "execution_model": config.execution_model, "end_of_data_policy": config.end_of_data_policy,
        },
        "summary": {
            "initial_balance": backtest_result.summary.initial_balance,
            "final_balance": backtest_result.summary.final_balance,
            "net_pnl": backtest_result.summary.net_pnl,
            "total_return": backtest_result.summary.total_return,
            "trade_count": backtest_result.summary.trade_count,
            "winning_trades": backtest_result.summary.winning_trades,
            "losing_trades": backtest_result.summary.losing_trades,
            "win_rate": backtest_result.summary.win_rate,
            "average_win": backtest_result.summary.average_win,
            "average_loss": backtest_result.summary.average_loss,
            "largest_win": backtest_result.summary.largest_win,
            "largest_loss": backtest_result.summary.largest_loss,
            "average_trade": backtest_result.summary.average_trade,
            "expectancy": backtest_result.summary.expectancy,
            "max_consecutive_wins": backtest_result.summary.max_consecutive_wins,
            "max_consecutive_losses": backtest_result.summary.max_consecutive_losses,
            "profit_factor": backtest_result.summary.profit_factor,
            "max_drawdown": backtest_result.summary.max_drawdown,
            "max_drawdown_percent": backtest_result.summary.max_drawdown_percent,
        },
        "trades": [
            {
                "trade_id": t.trade_id, "direction": t.direction,
                "signal_timestamp": t.signal_timestamp.isoformat(),
                "entry_timestamp": t.entry_timestamp.isoformat(), "entry_price": t.entry_price,
                "exit_timestamp": t.exit_timestamp.isoformat(), "exit_price": t.exit_price,
                "size": t.size, "gross_pnl": t.gross_pnl, "transaction_costs": t.transaction_costs,
                "net_pnl": t.net_pnl, "return_pct": t.return_pct,
                "entry_reason": t.entry_reason, "exit_reason": t.exit_reason,
            }
            for t in backtest_result.trades
        ],
        "equity_curve": [
            {
                "timestamp": p.timestamp.isoformat(), "balance": p.balance, "equity": p.equity,
                "drawdown": p.drawdown, "drawdown_percent": p.drawdown_percent,
            }
            for p in backtest_result.equity_curve
        ],
    }
