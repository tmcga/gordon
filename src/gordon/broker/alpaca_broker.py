"""Real equity broker via Alpaca."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar

import structlog

from gordon.core.enums import AssetClass, OrderType, Side, TimeInForce
from gordon.core.errors import BrokerError, OrderRejectedError
from gordon.core.models import Asset, Fill, Position

if TYPE_CHECKING:
    from collections.abc import Callable

    from gordon.core.models import Order

logger = structlog.get_logger()

T = TypeVar("T")

_TIF_MAP: dict[TimeInForce, str] = {
    TimeInForce.GTC: "gtc",
    TimeInForce.IOC: "ioc",
    TimeInForce.FOK: "fok",
    TimeInForce.DAY: "day",
}


class AlpacaBroker:
    """Real order routing through Alpaca for US equities.

    Requires ALPACA_API_KEY and ALPACA_API_SECRET.
    Uses paper trading by default for safety.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
    ) -> None:
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise ImportError(
                "alpaca-py is required for AlpacaBroker. Install it with: pip install alpaca-py"
            ) from exc

        if not api_key or not api_secret:
            raise BrokerError(
                "Alpaca API key and secret are required. "
                "Pass api_key/api_secret or set "
                "ALPACA_API_KEY / ALPACA_API_SECRET."
            )

        self._client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=paper,
        )

        logger.info("alpaca_broker_init", paper=paper)

    # -- Async helper ------------------------------------------------------

    async def _run_sync(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args))

    # -- Order management --------------------------------------------------

    async def submit_order(self, order: Order) -> Fill | None:
        """Submit order to Alpaca. Returns Fill when filled."""
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLimitOrderRequest,
            StopOrderRequest,
        )

        try:
            request = self._build_order_request(
                order,
                MarketOrderRequest,
                LimitOrderRequest,
                StopOrderRequest,
                StopLimitOrderRequest,
            )
            result = await self._run_sync(self._client.submit_order, request)
        except Exception as exc:
            msg = f"Alpaca order submission failed: {exc}"
            logger.error("alpaca_order_error", error=str(exc), order_id=order.id)
            if "forbidden" in str(exc).lower() or "rejected" in str(exc).lower():
                raise OrderRejectedError(msg, order_id=order.id) from exc
            raise BrokerError(msg) from exc

        logger.info(
            "alpaca_order_submitted",
            order_id=order.id,
            alpaca_id=str(result.id),
            symbol=order.asset.symbol,
            status=str(result.status),
        )

        # If the order filled immediately, return a Fill
        if str(result.status) == "filled" and result.filled_avg_price:
            return Fill(
                order_id=order.id,
                asset=order.asset,
                side=order.side,
                price=Decimal(str(result.filled_avg_price)),
                quantity=Decimal(str(result.filled_qty)),
                commission=Decimal("0"),
                timestamp=result.filled_at or datetime.now(tz=UTC),
            )

        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order on Alpaca."""
        try:
            await self._run_sync(self._client.cancel_order_by_id, order_id)
            logger.info("alpaca_order_cancelled", order_id=order_id)
            return True
        except Exception as exc:
            logger.warning(
                "alpaca_cancel_failed",
                order_id=order_id,
                error=str(exc),
            )
            return False

    async def get_positions(self) -> list[Position]:
        """Fetch current positions from Alpaca."""
        try:
            alpaca_positions = await self._run_sync(self._client.get_all_positions)
        except Exception as exc:
            raise BrokerError(f"Failed to fetch Alpaca positions: {exc}") from exc

        positions: list[Position] = []
        for pos in alpaca_positions:
            qty = Decimal(str(pos.qty))
            side_multiplier = Decimal("1") if str(pos.side) == "long" else Decimal("-1")

            positions.append(
                Position(
                    asset=Asset(
                        symbol=str(pos.symbol),
                        asset_class=AssetClass.EQUITY,
                    ),
                    quantity=qty * side_multiplier,
                    avg_entry_price=Decimal(str(pos.avg_entry_price)),
                    unrealized_pnl=Decimal(str(pos.unrealized_pl)),
                )
            )

        return positions

    async def get_fills(self, since: datetime | None = None) -> list[Fill]:
        """Fetch recent fills/trades from Alpaca."""
        from alpaca.trading.requests import GetOrdersRequest

        try:
            params = GetOrdersRequest(
                status="filled",
                after=since,
                limit=100,
            )
            orders = await self._run_sync(self._client.get_orders, params)
        except Exception as exc:
            raise BrokerError(f"Failed to fetch Alpaca fills: {exc}") from exc

        fills: list[Fill] = []
        for alpaca_order in orders:
            if not alpaca_order.filled_avg_price:
                continue
            fills.append(
                Fill(
                    order_id=str(alpaca_order.id),
                    asset=Asset(
                        symbol=str(alpaca_order.symbol),
                        asset_class=AssetClass.EQUITY,
                    ),
                    side=(Side.BUY if str(alpaca_order.side) == "buy" else Side.SELL),
                    price=Decimal(str(alpaca_order.filled_avg_price)),
                    quantity=Decimal(str(alpaca_order.filled_qty)),
                    commission=Decimal("0"),
                    timestamp=alpaca_order.filled_at or datetime.now(tz=UTC),
                )
            )

        return fills

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _build_order_request(
        order: Order,
        market_cls: type,
        limit_cls: type,
        stop_cls: type,
        stop_limit_cls: type,
    ):
        """Build an Alpaca order request from a Gordon Order."""
        common = {
            "symbol": order.asset.symbol,
            "qty": float(order.quantity),
            "side": order.side.value,
            "time_in_force": _TIF_MAP.get(order.time_in_force, "gtc"),
        }

        if order.order_type == OrderType.MARKET:
            return market_cls(**common)
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise OrderRejectedError(
                    "Limit order requires limit_price",
                    order_id=order.id,
                )
            return limit_cls(**common, limit_price=float(order.limit_price))
        if order.order_type == OrderType.STOP:
            if order.stop_price is None:
                raise OrderRejectedError(
                    "Stop order requires stop_price",
                    order_id=order.id,
                )
            return stop_cls(**common, stop_price=float(order.stop_price))
        if order.order_type == OrderType.STOP_LIMIT:
            if order.limit_price is None or order.stop_price is None:
                raise OrderRejectedError(
                    "Stop-limit order requires both limit_price and stop_price",
                    order_id=order.id,
                )
            return stop_limit_cls(
                **common,
                limit_price=float(order.limit_price),
                stop_price=float(order.stop_price),
            )

        raise OrderRejectedError(
            f"Unsupported order type: {order.order_type}",
            order_id=order.id,
        )
