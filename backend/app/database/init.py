"""Database schema initialization for the deployed Phase 0 application."""

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
