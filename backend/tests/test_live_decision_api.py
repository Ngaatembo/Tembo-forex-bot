from app.api.routes.live import live_decision


def test_live_decision_rejects_invalid_instrument():
    import asyncio
    try:
        asyncio.run(live_decision(instrument="BAD", timeframe="h1"))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("invalid instrument was accepted")


def test_live_decision_rejects_invalid_timeframe():
    import asyncio
    try:
        asyncio.run(live_decision(instrument="EUR/USD", timeframe="bad"))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("invalid timeframe was accepted")
