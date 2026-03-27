"""SQLAlchemy ORM models for trade persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all persistence models."""


class FillRecord(Base):
    """A persisted execution fill."""

    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    asset_class: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    price: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[str] = mapped_column(String(64))
    commission: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime]
    strategy_id: Mapped[str] = mapped_column(String(64), default="")


class TradeLog(Base):
    """A completed round-trip trade."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32))
    asset_class: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[str] = mapped_column(String(64))
    exit_price: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[str] = mapped_column(String(64))
    entry_time: Mapped[datetime]
    exit_time: Mapped[datetime]
    pnl: Mapped[str] = mapped_column(String(64))
    commission: Mapped[str] = mapped_column(String(64))
    strategy_id: Mapped[str] = mapped_column(String(64), default="")


class SnapshotRecord(Base):
    """A point-in-time portfolio snapshot."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime]
    cash: Mapped[str] = mapped_column(String(64))
    total_equity: Mapped[str] = mapped_column(String(64))
    unrealized_pnl: Mapped[str] = mapped_column(String(64))
    realized_pnl: Mapped[str] = mapped_column(String(64))
