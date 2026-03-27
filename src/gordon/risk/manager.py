"""Composable risk guard pipeline for pre-trade checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from gordon.core.protocols import RiskGuardProtocol, RiskVerdict

if TYPE_CHECKING:
    from gordon.core.models import Order, PortfolioSnapshot

log = structlog.get_logger(__name__)


class RiskManager:
    """Composable pipeline of risk guards applied before order execution.

    Guards are evaluated in order. If any guard rejects, the order is blocked.
    """

    def __init__(self, guards: list[RiskGuardProtocol] | None = None) -> None:
        self._guards: list[RiskGuardProtocol] = list(guards) if guards else []

    def add_guard(self, guard: RiskGuardProtocol) -> None:
        """Append a guard to the pipeline."""
        self._guards.append(guard)
        log.info("risk_manager.guard_added", guard=guard.name)

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        """Run all guards. Return first rejection or approval."""
        for guard in self._guards:
            verdict = guard.check(order, portfolio)
            if not verdict:
                log.warning(
                    "risk_manager.order_rejected",
                    order_id=order.id,
                    guard=guard.name,
                    reason=verdict.reason,
                )
                return verdict
        log.debug("risk_manager.order_approved", order_id=order.id)
        return RiskVerdict(True)

    def check_all(self, order: Order, portfolio: PortfolioSnapshot) -> list[RiskVerdict]:
        """Run all guards and return all verdicts (even after rejection)."""
        verdicts: list[RiskVerdict] = []
        for guard in self._guards:
            verdict = guard.check(order, portfolio)
            verdicts.append(verdict)
            if not verdict:
                log.info(
                    "risk_manager.check_all.rejection",
                    guard=guard.name,
                    reason=verdict.reason,
                )
        return verdicts
