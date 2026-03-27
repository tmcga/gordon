"""Tests for gordon.agent.prompts -- system prompt generation."""

from __future__ import annotations

from decimal import Decimal

from gordon.agent.prompts import SYSTEM_PROMPT, build_system_prompt
from gordon.agent.tools import AgentContext
from gordon.portfolio.tracker import PortfolioTracker


class _StubDataFeed:
    """Minimal stub for the data feed dependency."""


def test_system_prompt_is_nonempty_string() -> None:
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0


def test_build_system_prompt_includes_portfolio_info() -> None:
    tracker = PortfolioTracker(initial_cash=Decimal("100000"))
    feed = _StubDataFeed()
    ctx = AgentContext(tracker=tracker, data_feed=feed)  # type: ignore[arg-type]

    prompt = build_system_prompt(ctx)

    assert "Cash: 100000" in prompt
    assert "Total equity:" in prompt
    assert "No open positions" in prompt
    assert "NOT CONFIGURED" in prompt  # broker is None
