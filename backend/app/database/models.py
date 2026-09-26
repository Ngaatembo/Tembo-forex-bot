undefined

class PaperRuntimeState(Base):
    """Persistent state for the live-data paper runtime.

    This table contains simulated state only. It has no broker/order fields
    and is intentionally separate from the historical demonstration snapshot.
    """
    __tablename__ = "paper_runtime_states"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    initial_equity: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_start_equity: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    peak_equity: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PaperRuntimePosition(Base):
    """Persistent paper position; never maps to a broker position."""
    __tablename__ = "paper_runtime_positions"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_size: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_config_id: Mapped[str] = mapped_column(String, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    periods_held: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_holding_periods: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")


class PaperRuntimeTrade(Base):
    """Immutable closed paper-trade audit record."""
    __tablename__ = "paper_runtime_trades"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trade_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    position_id: Mapped[str] = mapped_column(String, nullable=False)
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    position_size: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_reason: Mapped[str] = mapped_column(String, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_config_id: Mapped[str] = mapped_column(String, nullable=False)
