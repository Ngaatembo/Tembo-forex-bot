"""Application configuration.

Loads all runtime configuration from environment variables.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Forex Research Platform"
    environment: str = "development"
    debug: bool = True
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/ai_trading"

    market_data_provider: str = "mock"
    market_data_api_key: Optional[str] = None
    market_data_account_id: Optional[str] = None
    deriv_public_ws_url: Optional[str] = "wss://api.derivws.com/trading/v1/options/ws/public"
    deriv_api_token: Optional[str] = None
    deriv_app_id: Optional[str] = None
    deriv_account_id: Optional[str] = None
    deriv_trading_mode: str = "demo"
    # Comma-separated research config IDs that may be FORWARD-TESTED on the
    # paper runtime and the Deriv demo account while their research gate is
    # still PROMISING. Set to an empty value (or "none") to switch it off.
    # Every other gate (live signal, macro risk, full risk hierarchy) still
    # applies, and forward tests use half the normal per-trade risk.
    # Experiment 4 (2026-09-29): USD/JPY H1 breakout passed 2012-2022 and 2026 data;
    # the gold H1 breakout failed both under the live exits, so it was replaced.
    demo_forward_test_configs: str = "vsc_exp4_usdjpy_h1_breakout_55"
    # Phone alerts (Web Push): heads-up 5 minutes before an H1 candle closes
    # when a signal is forming, then the confirmed result after the close.
    enable_alerts: bool = True
    alerts_vapid_subject: str = "https://tembobot.ngaatendwew.workers.dev"
    mt5_bridge_url: Optional[str] = None
    mt5_bridge_token: Optional[str] = None
    news_provider: str = "mock"
    news_api_key: Optional[str] = None
    economic_calendar_provider: str = "mock"
    economic_calendar_api_key: Optional[str] = None

    ai_provider: str = "anthropic"
    ai_api_key: Optional[str] = None
    ai_model: str = "claude-sonnet-5"

    enable_live_execution: bool = False
    enable_historical_bootstrap: bool = False

    enable_paper_runtime: bool = False
    paper_runtime_interval_seconds: int = 900

    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_weekly_loss_pct: float = 6.0
    max_drawdown_pct: float = 10.0
    max_open_positions: int = 5
    max_leverage: float = 10.0

    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    alert_email: Optional[str] = None
    secret_key: str = "change-me-in-env"
    access_token_expire_minutes: int = 60
    admin_download_token: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
