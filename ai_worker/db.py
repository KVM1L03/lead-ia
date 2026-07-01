"""SQLAlchemy async session factory for the ai_worker process.

Used only by persist_phase_result_activity to update the app.runs table.
RunRow is defined in shared/db.py and imported here for ORM access.
Engine is created lazily — no import-time connection attempt.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.db import RunRow as RunRow

_APP_DATABASE_URL_DEFAULT = "postgresql+asyncpg://temporal:temporal@localhost:5432/temporal"


def _url() -> str:
    raw = os.environ.get("APP_DATABASE_URL", _APP_DATABASE_URL_DEFAULT)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


_engine = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (or lazily create) the process-wide async session factory."""
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_async_engine(_url(), echo=False, pool_pre_ping=True)
        _SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)
    return _SessionFactory
