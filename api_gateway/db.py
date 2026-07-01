"""SQLAlchemy async engine and session factory for the api_gateway process.

RunRow is defined in shared/db.py (imported by both api_gateway and ai_worker).
This module owns the engine, session dependency, and DDL startup helper.
Engine is created lazily so importing this module in test environments
(no asyncpg / no live DB) does not fail at import time.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.db import RunRow as RunRow
from shared.db import _Base

_APP_DATABASE_URL_DEFAULT = "postgresql+asyncpg://temporal:temporal@localhost:5432/temporal"


def _url() -> str:
    raw = os.environ.get("APP_DATABASE_URL", _APP_DATABASE_URL_DEFAULT)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


_engine = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None


def _session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_async_engine(_url(), echo=False, pool_pre_ping=True)
        _SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)
    return _SessionFactory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session (FastAPI dependency)."""
    factory = _session_factory()
    async with factory() as session:
        yield session


async def create_app_schema() -> None:
    """Create app schema + tables if they don't exist. Call at startup."""
    _session_factory()
    async with _engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        await conn.run_sync(_Base.metadata.create_all)
