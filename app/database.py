"""
PostgreSQL connection layer using SQLAlchemy async + asyncpg.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

load_dotenv()
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/open_ownership")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables():
    """Create all tables and run migrations on startup."""
    from app.models.user import User  # noqa: F401
    from app.models.application import Application  # noqa: F401
    from app.models.audit_log import AuditLog  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns that may be missing on existing tables
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_notif_read TIMESTAMPTZ")
        )
    logger.info("Database tables created/verified.")
