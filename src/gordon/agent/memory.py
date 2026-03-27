"""Conversation and market observation memory backed by SQLite."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    """Declarative base for agent memory tables."""


class MessageRow(_Base):
    """A single conversation message (user / assistant / system)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
    )


class ObservationRow(_Base):
    """A market observation or decision rationale."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observation: Mapped[str] = mapped_column(Text)
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    timestamp: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class AgentMemory:
    """Persistent memory for the AI agent.

    Stores conversation history and market observations in SQLite.
    """

    def __init__(self, db_url: str = "sqlite:///gordon_agent.db") -> None:
        self._engine = create_engine(db_url, echo=False)
        _Base.metadata.create_all(self._engine)
        log.info("agent_memory.initialized", db_url=db_url)

    # -- messages -----------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Record a conversation message (user/assistant/system)."""
        with Session(self._engine) as session:
            session.add(MessageRow(role=role, content=content))
            session.commit()

    def get_messages(self, limit: int = 50) -> list[dict[str, str]]:
        """Get recent conversation messages as [{"role": ..., "content": ...}, ...]."""
        with Session(self._engine) as session:
            rows = session.query(MessageRow).order_by(MessageRow.id.desc()).limit(limit).all()
        # Return in chronological order (oldest first).
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def clear_messages(self) -> None:
        """Clear conversation history (keep observations)."""
        with Session(self._engine) as session:
            session.query(MessageRow).delete()
            session.commit()
        log.info("agent_memory.messages_cleared")

    # -- observations -------------------------------------------------------

    def add_observation(
        self,
        observation: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a market observation or decision rationale."""
        ctx = json.dumps(context or {})
        with Session(self._engine) as session:
            session.add(ObservationRow(observation=observation, context_json=ctx))
            session.commit()

    def get_observations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent observations."""
        with Session(self._engine) as session:
            rows = (
                session.query(ObservationRow).order_by(ObservationRow.id.desc()).limit(limit).all()
            )
        return [
            {
                "observation": r.observation,
                "context": json.loads(r.context_json),
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in reversed(rows)
        ]

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Dispose of the engine."""
        self._engine.dispose()
        log.info("agent_memory.closed")
