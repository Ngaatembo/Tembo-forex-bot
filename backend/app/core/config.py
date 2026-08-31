"""
Application configuration.

Loads all runtime configuration from environment variables.
No secrets are ever hard-coded here — see .env.example for the
full list of variables this application expects.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "AI Forex Research Platform"
    environment: str = "development"  # development | staging | production
    debug: bool = True

    # --- CORS ---
    # Comma-separated list of frontend origins allowed to call this API.
    # The frontend NEVER needs a secret to be in this list -- CORS is
    # about which origins the browser permits to receive responses, not
    # authentication. Defaults to common local-dev ports; set the real
    # Vercel URL here in production via the CORS_ALLOWED_ORIGINS env var.
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/ai_trading"

    # --- Market data provider ---
    market_data_provider: str = "mock"  # mock | oanda | ig | fxcm | interactive_brokers
    market_data_api_key: Optional[str] = None
    market_data_account_id: Optional[str] = None

    # --- News provider ---
    news_provider: str = "mock"
    news_api_key: Optional[str] = None

    # --- Economic calendar provider ---
    economic_calendar_provider: str = "mock"
    economic_calendar_api_key: Optional[str] = None

    # --- AI provider ---
    ai_provider: str = "anthropic"
    ai_api_key: Optional[str] = None
    ai_model: str = "claude-sonnet-5"

    # --- Risk / safety ---
    # Hard safety switch. Must be explicitly and deliberately set to true
    # in a production environment to allow the live broker adapter to be
    # constructed at all. Defaults to false everywhere, including prod.
    enable_live_execution: bool = False

    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_weekly_loss_pct: float = 6.0
    max_drawdown_pct: float = 10.0
    max_open_positions: int = 5
    max_leverage: float = 10.0

    # --- Alerts (optional, Phase 5+) ---
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    alert_email: Optional[str] = None

    # --- Auth (Phase 9+) ---
    secret_key: str = "change-me-in-env"
    access_token_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
