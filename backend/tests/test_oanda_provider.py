from app.data_engine.providers.oanda import _GRANULARITY_MAP


def test_oanda_timeframes_match_tembo_cockpit():
    assert _GRANULARITY_MAP == {
        "m5": "M5",
        "m15": "M15",
        "h1": "H1",
        "h4": "H4",
        "d1": "D",
    }
