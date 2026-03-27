"""Trade store — persists fills, trades, and snapshots to SQLite."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gordon.core.enums import AssetClass, Side
from gordon.core.models import Asset, Fill, PortfolioSnapshot, TradeRecord
from gordon.persistence.models import Base, FillRecord, SnapshotRecord, TradeLog

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class TradeStore:
    """SQLite-backed persistence for trading activity.

    Converts between Gordon domain models and SQLAlchemy ORM records,
    storing ``Decimal`` values as strings to preserve precision.
    """

    def __init__(self, db_url: str = "sqlite:///gordon_trades.db") -> None:
        self._engine = create_engine(db_url)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(self._engine)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def record_fill(self, fill: Fill, strategy_id: str = "") -> None:
        """Persist a :class:`~gordon.core.models.Fill` to the database."""
        record = FillRecord(
            order_id=fill.order_id,
            symbol=fill.asset.symbol,
            asset_class=fill.asset.asset_class.value,
            side=fill.side.value,
            price=str(fill.price),
            quantity=str(fill.quantity),
            commission=str(fill.commission),
            timestamp=fill.timestamp,
            strategy_id=strategy_id,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
        logger.debug("Recorded fill for %s (%s)", fill.asset.symbol, fill.order_id)

    def record_trade(self, trade: TradeRecord) -> None:
        """Persist a completed :class:`~gordon.core.models.TradeRecord`."""
        record = TradeLog(
            symbol=trade.asset.symbol,
            asset_class=trade.asset.asset_class.value,
            side=trade.side.value,
            entry_price=str(trade.entry_price),
            exit_price=str(trade.exit_price),
            quantity=str(trade.quantity),
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            pnl=str(trade.pnl),
            commission=str(trade.commission),
            strategy_id=trade.strategy_id,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
        logger.debug("Recorded trade for %s (pnl=%s)", trade.asset.symbol, trade.pnl)

    def record_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        """Persist a :class:`~gordon.core.models.PortfolioSnapshot`."""
        record = SnapshotRecord(
            timestamp=snapshot.timestamp,
            cash=str(snapshot.cash),
            total_equity=str(snapshot.total_equity),
            unrealized_pnl=str(snapshot.unrealized_pnl),
            realized_pnl=str(snapshot.realized_pnl),
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
        logger.debug("Recorded snapshot at %s", snapshot.timestamp)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_fills(
        self,
        symbol: str | None = None,
        since: datetime | None = None,
    ) -> list[Fill]:
        """Query fills with optional filters.

        Returns domain :class:`~gordon.core.models.Fill` objects.
        """
        stmt = select(FillRecord)
        if symbol is not None:
            stmt = stmt.where(FillRecord.symbol == symbol)
        if since is not None:
            stmt = stmt.where(FillRecord.timestamp >= since)
        stmt = stmt.order_by(FillRecord.timestamp)

        with self._session_factory() as session:
            rows = session.scalars(stmt).all()

        return [self._fill_from_record(r) for r in rows]

    def get_trades(
        self,
        symbol: str | None = None,
    ) -> list[TradeRecord]:
        """Query completed trades.

        Returns domain :class:`~gordon.core.models.TradeRecord` objects.
        """
        stmt = select(TradeLog)
        if symbol is not None:
            stmt = stmt.where(TradeLog.symbol == symbol)
        stmt = stmt.order_by(TradeLog.entry_time)

        with self._session_factory() as session:
            rows = session.scalars(stmt).all()

        return [self._trade_from_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Dispose of the engine and release resources."""
        self._engine.dispose()
        logger.debug("TradeStore engine disposed")

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_from_record(record: FillRecord) -> Fill:
        return Fill(
            order_id=record.order_id,
            asset=Asset(
                symbol=record.symbol,
                asset_class=AssetClass(record.asset_class),
            ),
            side=Side(record.side),
            price=Decimal(record.price),
            quantity=Decimal(record.quantity),
            commission=Decimal(record.commission),
            timestamp=record.timestamp,
        )

    @staticmethod
    def _trade_from_record(record: TradeLog) -> TradeRecord:
        return TradeRecord(
            asset=Asset(
                symbol=record.symbol,
                asset_class=AssetClass(record.asset_class),
            ),
            side=Side(record.side),
            entry_price=Decimal(record.entry_price),
            exit_price=Decimal(record.exit_price),
            quantity=Decimal(record.quantity),
            entry_time=record.entry_time,
            exit_time=record.exit_time,
            pnl=Decimal(record.pnl),
            commission=Decimal(record.commission),
            strategy_id=record.strategy_id,
        )
