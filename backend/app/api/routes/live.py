"""Read-only contract for the live trading cockpit.

It deliberately exposes no order-placement operation. Until an MT5
terminal/bridge is connected and verified, missing market data produces
NO_TRADE rather than fabricated prices or signals.
"""
from fastapi import APIRouter, Query
from app.api.routes.health import health_check
from app.core.config import get_settings

router = APIRouter(prefix="/live", tags=["live"])
INSTRUMENTS = ("EUR/USD", "GBP/USD", "XAU/USD")

@router.get("/overview")
async def live_overview(
    instrument: str = Query("EUR/USD"),
    timeframe: str = Query("h1"),
) -> dict:
    settings = get_settings()
    health = await health_check()
    selected = instrument if instrument in INSTRUMENTS else "EUR/USD"
    provider = settings.market_data_provider
    data_status = health["market_data"]
    decision = "NO_TRADE"
    reason = "Live market data is not verified, so Tembo fails closed instead of inventing an entry."
    return {
        "mode": "MT5_DEMO_READY" if settings.mt5_bridge_url else "PREPARING",
        "mt5": {
            "status": "configured" if settings.mt5_bridge_url and settings.mt5_bridge_token else "not_connected",
            "message": "Bridge configuration exists; terminal connectivity will be verified when the bridge is deployed."
            if settings.mt5_bridge_url else "Waiting for the MT5 bridge URL and token.",
        },
        "execution": {
            "enabled": bool(settings.enable_live_execution),
            "note": "Execution remains disabled until MT5 demo connectivity and safety tests are completed.",
        },
        "market_data": {"provider": provider, "status": data_status},
        "context": {
            "news": health["news_service"],
            "calendar": "configured" if settings.economic_calendar_provider != "mock" else "mock",
        },
        "instruments": [{
            "instrument": symbol,
            "timeframe": timeframe,
            "provider": provider,
            "data_status": data_status,
            "current_price": None,
            "last_update": None,
            "decision": decision,
            "reason": reason,
        } for symbol in INSTRUMENTS],
        "trade_plan": {
            "instrument": selected,
            "decision": decision,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "reason": reason,
        },
    }
