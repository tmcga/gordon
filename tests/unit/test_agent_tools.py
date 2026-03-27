"""Tests for gordon.agent.tools -- tool definitions and execute_tool dispatch."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from gordon.agent.tools import TOOLS, AgentContext, execute_tool
from gordon.portfolio.tracker import PortfolioTracker

# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_tools_list_has_seven_tools() -> None:
    assert len(TOOLS) == 7


@pytest.mark.parametrize("tool", TOOLS, ids=[t["name"] for t in TOOLS])
def test_each_tool_has_required_keys(tool: dict) -> None:
    assert "name" in tool
    assert "description" in tool
    assert "input_schema" in tool
    assert isinstance(tool["name"], str)
    assert isinstance(tool["description"], str)
    assert isinstance(tool["input_schema"], dict)


# ---------------------------------------------------------------------------
# AgentContext creation
# ---------------------------------------------------------------------------


class _StubDataFeed:
    """Minimal stub satisfying the BaseDataFeed type hint."""


def test_agent_context_creation() -> None:
    tracker = PortfolioTracker(initial_cash=Decimal("100000"))
    feed = _StubDataFeed()
    ctx = AgentContext(tracker=tracker, data_feed=feed)  # type: ignore[arg-type]

    assert ctx.tracker is tracker
    assert ctx.data_feed is feed
    assert ctx.broker is None
    assert ctx.strategies == {}


# ---------------------------------------------------------------------------
# execute_tool tests
# ---------------------------------------------------------------------------


def _make_context() -> AgentContext:
    tracker = PortfolioTracker(initial_cash=Decimal("50000"))
    feed = _StubDataFeed()
    return AgentContext(tracker=tracker, data_feed=feed)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_execute_tool_list_strategies() -> None:
    ctx = _make_context()
    result = await execute_tool("list_strategies", {}, ctx)
    data = json.loads(result)
    assert "strategies" in data
    assert "count" in data
    assert isinstance(data["strategies"], list)


@pytest.mark.asyncio
async def test_execute_tool_get_portfolio_status() -> None:
    ctx = _make_context()
    result = await execute_tool("get_portfolio_status", {}, ctx)
    data = json.loads(result)
    assert "cash" in data
    assert data["cash"] == "50000"
    assert "total_equity" in data
    assert "positions" in data


@pytest.mark.asyncio
async def test_execute_tool_unknown_tool_returns_error() -> None:
    ctx = _make_context()
    result = await execute_tool("no_such_tool", {}, ctx)
    data = json.loads(result)
    assert "error" in data
    assert "Unknown tool" in data["error"]
