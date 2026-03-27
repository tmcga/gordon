"""Rebalancer -- generate orders to move a portfolio toward target weights."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from gordon.core.enums import AssetClass, Side
from gordon.core.models import Asset, Position


@dataclass(frozen=True)
class RebalanceOrder:
    """A single order produced by the rebalancer."""

    asset: Asset
    side: Side
    quantity: Decimal
    reason: str


class Rebalancer:
    """Generate orders to move current portfolio toward target weights."""

    def rebalance(
        self,
        current_positions: dict[str, Position],
        target_weights: dict[str, float],
        total_equity: Decimal,
        prices: dict[str, Decimal],
        asset_class: AssetClass = AssetClass.EQUITY,
        min_trade_value: Decimal = Decimal("10"),
    ) -> list[RebalanceOrder]:
        """Compute orders needed to reach target allocation.

        For each asset:
        1. Compute target value = total_equity * target_weight
        2. Compute current value = position.quantity * price
        3. Diff -> BUY if under-allocated, SELL if over-allocated
        4. Skip if abs(diff) < min_trade_value
        """
        orders: list[RebalanceOrder] = []

        # All symbols that appear in either targets or current positions
        all_symbols = set(target_weights) | set(current_positions)

        for symbol in sorted(all_symbols):
            weight = target_weights.get(symbol, 0.0)
            target_value = total_equity * Decimal(str(weight))

            pos = current_positions.get(symbol)
            price = prices.get(symbol)

            if price is None or price <= 0:
                continue

            current_value = pos.quantity * price if pos is not None else Decimal("0")
            diff_value = target_value - current_value

            if abs(diff_value) < min_trade_value:
                continue

            quantity = abs(diff_value) / price

            if diff_value > 0:
                side = Side.BUY
                reason = f"Under-allocated: current {current_value:.2f}, target {target_value:.2f}"
            else:
                side = Side.SELL
                reason = f"Over-allocated: current {current_value:.2f}, target {target_value:.2f}"

            asset = pos.asset if pos is not None else Asset(symbol=symbol, asset_class=asset_class)

            orders.append(
                RebalanceOrder(
                    asset=asset,
                    side=side,
                    quantity=quantity,
                    reason=reason,
                )
            )

        return orders
