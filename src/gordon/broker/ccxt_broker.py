"""Real crypto broker via CCXT."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING, Any

import structlog

from gordon.core.enums import AssetClass, OrderType, Side
from gordon.core.errors import BrokerError, OrderRejectedError
from gordon.core.models import Asset, Fill, Position

if TYPE_CHECKING:
    from gordon.core.models import Order

logger = structlog.get_logger()


class CCXTBroker:
    """Real order routing through any CCXT-supported exchange.

    Requires API key/secret configured on the exchange.
    Defaults to sandbox (testnet) mode for safety.
    """

    def __init__(
        self,
        exchange: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        sandbox: bool = True,
    ) -> None:
        try:
            import ccxt
        except ImportError as exc:
            raise ImportError(
                "ccxt is required for CCXTBroker. Install it with: pip install ccxt"
            ) from exc

        exchange_cls = getattr(ccxt, exchange, None)
        if exchange_cls is None:
            raise BrokerError(f"Unsupported CCXT exchange: {exchange}")

        config: dict[str, Any] = {}
        if api_key:
            config["apiKey"] = api_key
        if api_secret:
            config["secret"] = api_secret

        self._exchange = exchange_cls(config)
        if sandbox:
            self._exchange.set_sandbox_mode(True)

        self._exchange_name = exchange
        self._sandbox = sandbox

        logger.info(
            "ccxt_broker_init",
            exchange=exchange,
            sandbox=sandbox,
        )

    # -- Order management --------------------------------------------------

    async def submit_order(self, order: Order) -> Fill | None:
        """Submit order to the exchange. Returns Fill on success."""
        symbol = self._to_ccxt_symbol(order.asset)
        side = order.side.value  # "buy" or "sell"
        order_type = self._to_ccxt_order_type(order.order_type)
        amount = float(order.quantity)
        price = float(order.limit_price) if order.limit_price else None

        try:
            result = await self._run_sync(
                self._exchange.create_order,
                symbol,
                order_type,
                side,
                amount,
                price,
            )
        except Exception as exc:
            msg = f"CCXT order submission failed: {exc}"
            logger.error("ccxt_order_error", error=str(exc), order_id=order.id)
            if "insufficient" in str(exc).lower():
                raise OrderRejectedError(msg, order_id=order.id) from exc
            raise BrokerError(msg) from exc

        logger.info(
            "ccxt_order_submitted",
            order_id=order.id,
            exchange_id=result.get("id"),
            symbol=symbol,
            side=side,
            status=result.get("status"),
        )

        # If the order was filled immediately, return a Fill
        status = result.get("status", "")
        if status == "closed" and result.get("filled"):
            return self._parse_fill(result, order)

        # For partial or open orders, no fill yet
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order on the exchange."""
        try:
            await self._run_sync(self._exchange.cancel_order, order_id)
            logger.info("ccxt_order_cancelled", order_id=order_id)
            return True
        except Exception as exc:
            logger.warning(
                "ccxt_cancel_failed",
                order_id=order_id,
                error=str(exc),
            )
            return False

    async def get_positions(self) -> list[Position]:
        """Fetch current positions from the exchange."""
        try:
            balances = await self._run_sync(self._exchange.fetch_balance)
        except Exception as exc:
            raise BrokerError(f"Failed to fetch positions: {exc}") from exc

        positions: list[Position] = []
        total: dict[str, Any] = balances.get("total", {})
        for symbol, amount in total.items():
            if amount and float(amount) != 0.0:
                positions.append(
                    Position(
                        asset=Asset(
                            symbol=symbol,
                            asset_class=AssetClass.CRYPTO,
                            exchange=self._exchange_name,
                        ),
                        quantity=Decimal(str(amount)),
                        avg_entry_price=Decimal("0"),
                    )
                )

        return positions

    async def get_fills(self, since: datetime | None = None) -> list[Fill]:
        """Fetch recent fills/trades from the exchange."""
        since_ms = int(since.timestamp() * 1000) if since else None

        try:
            trades = await self._run_sync(
                self._exchange.fetch_my_trades,
                None,  # symbol — None for all
                since_ms,
            )
        except Exception as exc:
            raise BrokerError(f"Failed to fetch fills: {exc}") from exc

        fills: list[Fill] = []
        for trade in trades:
            ccxt_symbol: str = trade.get("symbol", "")
            base = ccxt_symbol.split("/")[0] if "/" in ccxt_symbol else ccxt_symbol

            fills.append(
                Fill(
                    order_id=trade.get("order", ""),
                    asset=Asset(
                        symbol=base,
                        asset_class=AssetClass.CRYPTO,
                        exchange=self._exchange_name,
                    ),
                    side=Side.BUY if trade.get("side") == "buy" else Side.SELL,
                    price=Decimal(str(trade.get("price", 0))),
                    quantity=Decimal(str(trade.get("amount", 0))),
                    commission=Decimal(str(trade.get("fee", {}).get("cost", 0) or 0)),
                    timestamp=datetime.fromtimestamp(trade["timestamp"] / 1000, tz=UTC)
                    if trade.get("timestamp")
                    else datetime.now(tz=UTC),
                )
            )

        return fills

    # -- Helpers -----------------------------------------------------------

    def _to_ccxt_symbol(self, asset: Asset) -> str:
        """Convert Gordon Asset to CCXT symbol format (e.g. BTC/USDT).

        If the symbol already contains '/', return as-is.
        Otherwise, try common quote currencies.
        """
        if "/" in asset.symbol:
            return asset.symbol
        # Default to USDT quote for bare symbols
        return f"{asset.symbol}/USDT"

    @staticmethod
    def _to_ccxt_order_type(order_type: OrderType) -> str:
        """Map Gordon OrderType to CCXT order type string."""
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
        }
        result = mapping.get(order_type)
        if result is None:
            raise OrderRejectedError(f"Unsupported order type for CCXT: {order_type}")
        return result

    def _parse_fill(self, trade: dict[str, Any], order: Order) -> Fill:
        """Convert CCXT trade/order response to Gordon Fill."""
        fee_cost = 0
        fee = trade.get("fee")
        if isinstance(fee, dict):
            fee_cost = fee.get("cost", 0) or 0

        ts = trade.get("timestamp")
        fill_ts = datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else datetime.now(tz=UTC)

        return Fill(
            order_id=order.id,
            asset=order.asset,
            side=order.side,
            price=Decimal(str(trade.get("average", trade.get("price", 0)))),
            quantity=Decimal(str(trade.get("filled", order.quantity))),
            commission=Decimal(str(fee_cost)),
            timestamp=fill_ts,
        )

    @staticmethod
    async def _run_sync(fn: Any, *args: Any) -> Any:
        """Run a synchronous CCXT call in an executor thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args))
