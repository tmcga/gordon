"""Tests for the RiskManager pipeline."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gordon.core.enums import AssetClass, OrderType, Side
from gordon.core.models import Asset, Order, PortfolioSnapshot
from gordon.core.protocols import RiskVerdict
from gordon.risk.guards import MaxPositionSizeGuard, SymbolWhitelistGuard
from gordon.risk.manager import RiskManager


def _order() -> Order:
    return Order(
        asset=Asset(symbol="AAPL", asset_class=AssetClass.EQUITY),
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("10"),
        limit_price=Decimal("150"),
        strategy_id="test",
    )


def _portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2025, 1, 15),
        cash=Decimal("100000"),
        total_equity=Decimal("100000"),
    )


class _AlwaysApproveGuard:
    name = "always_approve"

    def check(self, order, portfolio) -> RiskVerdict:
        return RiskVerdict(True)


class _AlwaysRejectGuard:
    name = "always_reject"

    def check(self, order, portfolio) -> RiskVerdict:
        return RiskVerdict(False, "rejected by test guard")


class _CountingGuard:
    """Tracks how many times check() is called."""

    name = "counting"

    def __init__(self):
        self.call_count = 0

    def check(self, order, portfolio) -> RiskVerdict:
        self.call_count += 1
        return RiskVerdict(True)


class TestRiskManager:
    def test_no_guards_approves_everything(self):
        rm = RiskManager(guards=[])
        verdict = rm.check(_order(), _portfolio())
        assert verdict.approved is True

    def test_single_guard_approves(self):
        rm = RiskManager(guards=[_AlwaysApproveGuard()])
        verdict = rm.check(_order(), _portfolio())
        assert verdict.approved is True

    def test_single_guard_rejects(self):
        rm = RiskManager(guards=[_AlwaysRejectGuard()])
        verdict = rm.check(_order(), _portfolio())
        assert verdict.approved is False
        assert "rejected by test guard" in verdict.reason

    def test_check_short_circuits_on_first_rejection(self):
        counter = _CountingGuard()
        rm = RiskManager(guards=[_AlwaysRejectGuard(), counter])
        verdict = rm.check(_order(), _portfolio())
        assert verdict.approved is False
        assert counter.call_count == 0  # never reached

    def test_check_all_returns_all_verdicts(self):
        rm = RiskManager(
            guards=[_AlwaysApproveGuard(), _AlwaysRejectGuard(), _AlwaysApproveGuard()]
        )
        verdicts = rm.check_all(_order(), _portfolio())
        assert len(verdicts) == 3
        assert verdicts[0].approved is True
        assert verdicts[1].approved is False
        assert verdicts[2].approved is True

    def test_add_guard(self):
        rm = RiskManager()
        rm.add_guard(_AlwaysRejectGuard())
        verdict = rm.check(_order(), _portfolio())
        assert verdict.approved is False

    def test_with_real_guards(self):
        """Integration-style: compose real guards together."""
        rm = RiskManager(
            guards=[
                SymbolWhitelistGuard(symbols={"AAPL", "MSFT"}),
                MaxPositionSizeGuard(max_pct=0.10),
            ]
        )
        verdict = rm.check(_order(), _portfolio())
        assert verdict.approved is True
