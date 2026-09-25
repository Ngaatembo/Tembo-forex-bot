"""
Tembo MT5 read-only bridge.

Run this on the same Windows machine/VPS as the MetaTrader 5 terminal.
It intentionally exposes market-data operations only. No order endpoint
exists in this first phase.
"""

import os
from contextlib import asynccontextmanager

import MetaTrader5 as mt5
from fastapi import Depends, FastAPI, Header, HTTPException, Query


BRIDGE_TOKEN = os.environ.get("MT5_BRIDGE_TOKEN")
MT5_PATH = os.environ.get("MT5_PATH")
MT5_LOGIN = os.environ.get("MT5_LOGIN")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD")
MT5_SERVER = os.environ.get("MT5_SERVER")

TIMEFRAMES = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not BRIDGE_TOKEN:
        raise HTTPException(status_code=503, detail="MT5 bridge token is not configured.")
    if authorization != f"Bearer {BRIDGE_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized.")


def connect_terminal() -> None:
    kwargs = {}
    if MT5_LOGIN:
        kwargs["login"] = int(MT5_LOGIN)
    if MT5_PASSWORD:
        kwargs["password"] = MT5_PASSWORD
    if MT5_SERVER:
        kwargs["server"] = MT5_SERVER

    initialized = mt5.initialize(MT5_PATH, **kwargs) if MT5_PATH else mt5.initialize(**kwargs)
    if not initialized:
        raise RuntimeError(f"MetaTrader 5 initialize failed: {mt5.last_error()}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    connect_terminal()
    yield
    mt5.shutdown()


app = FastAPI(
    title="Tembo MT5 Bridge",
    description="Read-only market-data bridge between Tembo and a MetaTrader 5 terminal.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", dependencies=[Depends(require_token)])
def health() -> dict:
    terminal = mt5.terminal_info()
    account = mt5.account_info()
    if terminal is None or account is None:
        raise HTTPException(status_code=503, detail=f"MT5 information unavailable: {mt5.last_error()}")

    return {
        "status": "ok",
        "terminal_connected": True,
        "terminal_version": list(mt5.version()) if mt5.version() else None,
        "account_login": int(account.login),
        "account_server": account.server,
        "trade_allowed": bool(account.trade_allowed),
    }


@app.get("/price", dependencies=[Depends(require_token)])
def price(symbol: str = Query(..., min_length=1)) -> dict:
    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"MT5 symbol unavailable: {symbol}")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise HTTPException(status_code=503, detail=f"No tick available for {symbol}: {mt5.last_error()}")

    return {
        "symbol": symbol,
        "time": int(tick.time),
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "mid": (float(tick.bid) + float(tick.ask)) / 2.0,
    }


@app.get("/candles", dependencies=[Depends(require_token)])
def candles(
    symbol: str = Query(..., min_length=1),
    timeframe: str = Query(..., pattern="^(M5|M15|H1|H4|D1)$"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")

    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"MT5 symbol unavailable: {symbol}")

    # Start at position 1 so the current still-forming bar is excluded.
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[timeframe], 1, limit)
    if rates is None:
        raise HTTPException(status_code=503, detail=f"Could not read candles: {mt5.last_error()}")

    result = []
    for row in rates:
        result.append(
            {
                "time": int(row["time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": int(row["tick_volume"]),
                "real_volume": int(row["real_volume"]),
                "spread": int(row["spread"]),
            }
        )

    return {"symbol": symbol, "timeframe": timeframe, "candles": result}
