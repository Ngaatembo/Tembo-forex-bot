"""Database schema initialization for the deployed Phase 0 application."""

from sqlalchemy import text

from app.database.models import Base
from app.database.session import engine


async def initialize_database() -> None:
    """Create any missing SQLAlchemy tables on application startup.

    This is intentionally idempotent: existing tables and data are left
    untouched. It bootstraps the empty Render PostgreSQL instance while the
    project is still in its foundational phase.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent schema patch for paper runtime state added after the
        # foundational tables were first deployed.
        await conn.execute(text(
            "ALTER TABLE paper_runtime_states "
            "ADD COLUMN IF NOT EXISTS daily_realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0"
        ))
        await conn.execute(text(
            "ALTER TABLE paper_runtime_states "
            "ADD COLUMN IF NOT EXISTS session_date VARCHAR NOT NULL DEFAULT '1970-01-01'"
        ))
        await conn.execute(text(
            "ALTER TABLE paper_runtime_positions "
            "ADD COLUMN IF NOT EXISTS last_completed_candle_at TIMESTAMPTZ"
        ))
