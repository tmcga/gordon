"""Portfolio analytics -- allocation summaries and sector exposure."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gordon.core.models import Position


def portfolio_summary(
    positions: dict[str, Position],
    total_equity: Decimal,
) -> dict[str, Any]:
    """Summary of current portfolio allocation.

    Returns a dict with:
    - ``positions``: list of per-position dicts (symbol, quantity, value,
      weight, unrealized_pnl)
    - ``total_equity``: the portfolio equity
    - ``position_count``: number of positions
    - ``cash_weight``: inferred cash weight (1 - sum of position weights)
    """
    items: list[dict[str, Any]] = []
    total_position_value = Decimal("0")

    for symbol, pos in sorted(positions.items()):
        value = pos.market_value
        weight = float(value / total_equity) if total_equity > 0 else 0.0
        items.append(
            {
                "symbol": symbol,
                "quantity": pos.quantity,
                "value": value,
                "weight": weight,
                "unrealized_pnl": pos.unrealized_pnl,
            }
        )
        total_position_value += value

    cash_weight = (
        float((total_equity - total_position_value) / total_equity) if total_equity > 0 else 1.0
    )

    return {
        "positions": items,
        "total_equity": total_equity,
        "position_count": len(items),
        "cash_weight": cash_weight,
    }


def sector_exposure(
    positions: dict[str, Position],
    sector_map: dict[str, str],
) -> dict[str, float]:
    """Aggregate position market values by sector.

    Returns a dict of sector -> weight (fraction of total position value).
    Positions whose symbol is not in *sector_map* are grouped under
    ``"Unknown"``.
    """
    sector_values: dict[str, Decimal] = {}
    total = Decimal("0")

    for symbol, pos in positions.items():
        sector = sector_map.get(symbol, "Unknown")
        value = pos.market_value
        sector_values[sector] = sector_values.get(sector, Decimal("0")) + value
        total += value

    if total == 0:
        return {}

    return {sector: float(val / total) for sector, val in sorted(sector_values.items())}
