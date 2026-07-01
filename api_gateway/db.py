"""SQLAlchemy async engine and ORM models for the api_gateway process.

Table: app.runs — written here at workflow start; read by the frontend
via Prisma as runs progress. Both services share the same Postgres container
but the api_gateway owns the schema (SQLAlchemy DDL, Prisma is read-only).

Engine is created lazily so importing this module in test environments
(no asyncpg / no live DB) does not fail at import time.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ── connection URL ────────────────────────────────────────────────────────────

_APP_DATABASE_URL_DEFAULT = "postgresql+asyncpg://temporal:temporal@localhost:5432/temporal"


def _url() -> str:
    raw = os.environ.get("APP_DATABASE_URL", _APP_DATABASE_URL_DEFAULT)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


# ── lazy engine / session factory ────────────────────────────────────────────

_engine = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None


def _session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_async_engine(_url(), echo=False, pool_pre_ping=True)
        _SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)
    return _SessionFactory


# ── ORM ──────────────────────────────────────────────────────────────────────


class _Base(DeclarativeBase):
    pass


class RunRow(_Base):
    """Mirrors the Prisma Run model — keep columns in sync with schema.prisma."""

    __tablename__ = "runs"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target_query: Mapped[str] = mapped_column(Text, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_context: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scraping")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session (FastAPI dependency)."""
    factory = _session_factory()
    async with factory() as session:
        yield session


# ── startup helper ────────────────────────────────────────────────────────────


async def create_app_schema() -> None:
    """Create app schema + tables if they don't exist. Call at startup."""
    _session_factory()  # ensure _engine is initialised
    async with _engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        await conn.run_sync(_Base.metadata.create_all)
