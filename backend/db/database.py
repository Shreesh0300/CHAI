"""
Asynchronous Database engine and session management for CHAI.
Supports PostgreSQL (via asyncpg or psycopg) and seamless local SQLite fallback for tests.
"""
import os
import asyncio
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from backend.config import get_settings
from backend.db.models import Base
from backend.shared.logger import get_logger

logger = get_logger(__name__)

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
_db_initialized: bool = False
_lock = asyncio.Lock()


def normalize_database_url(url: Optional[str] = None) -> str:
    """
    Normalizes a standard database URL into an async SQLAlchemy connection string.
    e.g. postgresql://... -> postgresql+asyncpg://...
    """
    raw = (url or get_settings().database_url or "").strip()
    if not raw:
        return "sqlite+aiosqlite:///chai_memory.db"

    # Normalize standard postgresql prefix to async driver
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    elif raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://"):]
    elif raw.startswith("sqlite://") and not raw.startswith("sqlite+aiosqlite://"):
        return "sqlite+aiosqlite://" + raw[len("sqlite://"):]

    return raw


def get_engine(url: Optional[str] = None) -> AsyncEngine:
    """Returns or creates the global AsyncEngine."""
    global _engine, _session_maker
    if _engine is None or url is not None:
        target_url = normalize_database_url(url)
        # Configure engine options
        engine_kwargs = {"echo": False}
        if "sqlite" in target_url:
            # SQLite does not support pool_pre_ping or multi-host arguments
            engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
        else:
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20

        _engine = create_async_engine(target_url, **engine_kwargs)
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
        logger.info(f"[DATABASE] Initialized async database engine for: {target_url.split('@')[-1] if '@' in target_url else target_url}")

    return _engine


async def init_db(engine: Optional[AsyncEngine] = None) -> bool:
    """
    Asynchronously creates all database tables if they do not exist.
    Safe and idempotent.
    """
    global _db_initialized
    active_engine = engine or get_engine()

    try:
        async with active_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_initialized = True
        logger.info("[DATABASE] Verified and created database schema tables.")
        return True
    except Exception as exc:
        logger.warning(f"[DATABASE] Could not connect to primary database ({exc}). Attempting resilient fallback...")
        # If primary PostgreSQL is unreachable in dev/test, fallback to local SQLite
        fallback_url = "sqlite+aiosqlite:///chai_memory.db"
        try:
            fallback_engine = get_engine(fallback_url)
            async with fallback_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _db_initialized = True
            logger.info("[DATABASE] Initialized fallback SQLite database schema successfully.")
            return True
        except Exception as fb_exc:
            logger.error(f"[DATABASE] Fallback database initialization failed: {fb_exc}")
            return False


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a transactional AsyncSession scope."""
    global _session_maker
    if _session_maker is None:
        get_engine()
    assert _session_maker is not None

    async with _session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
