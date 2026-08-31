"""
GET /markets/{instrument} — the smallest necessary route that actually
exercises the live MarketDataProvider abstraction (current price +
recent candles + instrument metadata), reusing validate_candles for
the returned batch. Read-only. No order-placement, no trading action
of any kind — this is a data-retrieval endpoint only.
"""

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.validator import validate_candles

router = APIRouter(tags=["markets"])

_VALID_TIMEFRAMES = {"m5", "m15", "h1", "h4", "d1"}


@router.get("/markets/{instrument:path}")
async def get_market(instrument: str, timeframe: str = "h1") -> dict:
    instrument = unquote(instrument)
    timeframe = timeframe.lower()
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe {timeframe!r}. Must be one of {sorted(_VALID_TIMEFRAMES)}.")

    settings = get_settings()
    try:
        provider = get_market_data_provider(settings.market_data_provider)
    except NotImplementedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Market data provider not configured: {e}")

    try:
        current_price = await provider.get_current_price(instrument)
        candles = await provider.get_candles(instrument, timeframe, limit=20)
        metadata = await provider.get_instrument_metadata(instrument)
    except Exception as e:
        detail = str(e)
        if "Unsupported" in type(e).__name__:
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(status_code=503, detail=f"Market data provider error: {detail}")

    validation = validate_candles(candles, timeframe=timeframe)

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "provider": settings.market_data_provider,
        "current_price": current_price,
        "instrument_metadata": {
            "symbol": metadata.symbol, "display_name": metadata.display_name,
            "pip_size": metadata.pip_size, "asset_class": metadata.asset_class,
        },
        "recent_candles": [
            {
                "timestamp": c.timestamp.isoformat(), "open": c.open, "high": c.high,
                "low": c.low, "close": c.close, "volume": c.volume,
            }
            for c in candles
        ],
        "data_quality": {
            "is_clean": validation.is_clean,
            "ohlc_violations": len(validation.ohlc_violations),
            "duplicate_timestamps": len(validation.duplicate_timestamps),
            "unexpected_gaps": len(validation.unexpected_gaps),
        },
    }
