Tembo MT5 Demo Bridge
======================

This is the Windows/VPS component that connects Tembo's Render backend to a MetaTrader 5 terminal.

Architecture
------------
Tembo Render backend -> HTTPS -> this bridge -> MetaTrader 5 terminal -> DEMO account

The first version is deliberately read-only:
- /health
- /price
- /candles

There is no order-placement endpoint yet.

Requirements
------------
- Windows PC or Windows VPS
- MetaTrader 5 desktop terminal
- A broker MT5 demo account
- Python 3.11 or 3.12
- The bridge token configured on both sides

The official MT5 Python integration connects Python to the installed MT5 terminal and provides price/bar access through initialize, symbol_info_tick, symbol_select and copy_rates_from_pos. See https://www.mql5.com/en/docs/python_metatrader5

Demo-first setup
----------------
1. Install MetaTrader 5.
2. Log into the DEMO account in the terminal.
3. Make sure the symbols you want are visible in Market Watch.
4. Create a strong MT5_BRIDGE_TOKEN.
5. Copy .env.example to .env and fill the bridge token.
6. Install dependencies with: pip install -r requirements.txt
7. Start with: uvicorn mt5_bridge:app --host 0.0.0.0 --port 8787

Do not expose port 8787 directly to the public internet. Put the bridge behind HTTPS and an access-control layer, or use a private network/tunnel.

Broker symbol names
-------------------
Tembo internal names are EUR/USD, GBP/USD, USD/JPY and XAU/USD. The bridge currently expects MT5 names EURUSD, GBPUSD, USDJPY and XAUUSD. If a broker uses suffixes such as EURUSDm, adjust the mapping before switching Tembo to mt5_bridge.

Important
---------
Keep Tembo ENABLE_LIVE_EXECUTION=false. This bridge has no trading endpoint, so the first milestone is only real demo market data.
