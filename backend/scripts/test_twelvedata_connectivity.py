"""
Real, read-only Twelve Data connectivity test. Run this manually
against a configured environment (e.g. `python -m scripts.test_twelvedata_connectivity`
in the Render Shell, or locally with a real .env). This is NOT run by
the automated test suite — it requires real credentials and a real
network call, deliberately kept separate from test_twelvedata_provider.py
(which is fully mocked and never touches the network).

Never prints the API key. Distinguishes four distinct states clearly:
CREDENTIALS_MISSING, INVALID_CREDENTIALS, PROVIDER_UNAVAILABLE, REAL_PRICE_RECEIVED.
"""

import asyncio


async def main():
    from app.core.config import get_settings

    settings = get_settings()

    print(f"MARKET_DATA_PROVIDER: {settings.market_data_provider}")
    print(f"MARKET_DATA_API_KEY present: {bool(settings.market_data_api_key)}")

    if settings.market_data_provider != "twelvedata":
        print(f"RESULT: SKIPPED — MARKET_DATA_PROVIDER is {settings.market_data_provider!r}, not 'twelvedata'.")
        return

    if not settings.market_data_api_key:
        print("RESULT: CREDENTIALS_MISSING — MARKET_DATA_API_KEY is not set.")
        return

    from app.data_engine.providers.twelvedata import (
        AuthenticationError, ProviderConnectionError, ProviderTimeoutError,
        RateLimitError, TwelveDataProvider, TwelveDataProviderError,
    )

    try:
        provider = TwelveDataProvider()
    except ValueError as e:
        print(f"RESULT: CREDENTIALS_MISSING — {e}")
        return

    try:
        price = await provider.get_current_price("EUR/USD")
        print(f"RESULT: REAL_PRICE_RECEIVED — EUR/USD price = {price}")
    except AuthenticationError:
        print("RESULT: INVALID_CREDENTIALS — Twelve Data rejected the API key (HTTP 401).")
    except RateLimitError:
        print("RESULT: PROVIDER_UNAVAILABLE — rate limited (HTTP 429). Try again later.")
    except (ProviderTimeoutError, ProviderConnectionError):
        print("RESULT: PROVIDER_UNAVAILABLE — network/timeout error reaching Twelve Data.")
    except TwelveDataProviderError as e:
        print(f"RESULT: PROVIDER_UNAVAILABLE — {e}")


if __name__ == "__main__":
    asyncio.run(main())
