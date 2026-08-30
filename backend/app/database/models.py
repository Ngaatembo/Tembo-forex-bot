"""
Foundational database schema (Phase 0).

This defines table structure only — no business logic lives here.
Every trade/signal-related table carries explicit timestamps to
preserve auditability, per the project's development rules
(never delete historical records to improve statistics).

Tables intentionally left as later-phase stubs (news_articles,
economic_events, ai_analyses, signals, orders, positions, trades,
paper_accounts, performance_metrics, risk_events) are declared now
so migrations can build on a stable foundation, even though most
engines that populate them don't exist until later phases.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # e.g. EUR/USD
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    asset_class: Mapped[str] = mapped_column(String, default="forex")
    pip_size: Mapped[float] = mapped_column(Float, default=0.0001)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        # One row per (symbol, timeframe, timestamp) — this is what
        # app/data_engine/storage.py's upsert conflicts against, so
        # re-running ingestion for an overlapping range never
        # duplicates a candle.
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_market_candle_identity"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 1m,5m,15m,1h,4h,1d
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[uuid.UUID] = uuid_pk()
    source: Mapped[str] = mapped_column(String, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Original publication time as reported by the source — never
    # overwritten. Backtests join on this field to prevent look-ahead bias.
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    affected_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    affected_asset: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)


class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    previous_value: Mapped[str | None] = mapped_column(String, nullable=True)
    forecast_value: Mapped[str | None] = mapped_column(String, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(String, nullable=True)
    importance: Mapped[str | None] = mapped_column(String, nullable=True)  # low/medium/high
    source: Mapped[str | None] = mapped_column(String, nullable=True)


class TechnicalFeature(Base):
    __tablename__ = "technical_features"

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    model: Mapped[str] = mapped_column(String, nullable=False)
    structured_output: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # BUY/SELL/WAIT
    score: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    supporting_factors: Mapped[dict] = mapped_column(JSONB, default=dict)
    conflicting_factors: Mapped[dict] = mapped_column(JSONB, default=dict)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    starting_balance: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = uuid_pk()
    paper_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_accounts.id"), nullable=False)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[uuid.UUID] = uuid_pk()
    scope: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "strategy:trend_v1"
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "kill_switch_triggered"
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    level: Mapped[str] = mapped_column(String, nullable=False)
    component: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
