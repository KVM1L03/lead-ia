"""Shared SQLAlchemy ORM model for the `app.runs` table.

Both api_gateway (inserts + status updates) and ai_worker (persist_phase_result_activity)
import RunRow from here. Each service creates its own engine + session in its own db.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _Base(DeclarativeBase):
    pass


class RunRow(_Base):
    """Mirrors the Prisma Run model — SQLAlchemy owns DDL, Prisma is read-only."""

    __tablename__ = "runs"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target_query: Mapped[str] = mapped_column(Text, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_context: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scraping")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Progress counters — updated by persist_phase_result_activity
    scraped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    qualified: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    emails_generated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # JSON-encoded list[Lead]; null until first persist, updated at each phase boundary
    leads_json: Mapped[str | None] = mapped_column(Text, nullable=True)
