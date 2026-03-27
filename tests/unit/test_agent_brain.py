"""Tests for gordon.agent.brain -- AgentBrain orchestrator."""

from __future__ import annotations

from typing import Any

import pytest

from gordon.agent.brain import AgentBrain, AgentContext
from gordon.agent.memory import AgentMemory

# ---------------------------------------------------------------------------
# Mock AI provider (simple class, no unittest.mock)
# ---------------------------------------------------------------------------


class MockProvider:
    """A fake AIProvider that returns pre-configured responses in order."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_price",
        "description": "Get current price",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def _text_response(text: str) -> dict[str, Any]:
    """Build a provider response containing only a text block."""
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "model": "mock",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _tool_call_response(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_use_id: str = "call_1",
) -> dict[str, Any]:
    """Build a provider response containing a single tool_use block."""
    return {
        "content": [
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": tool_name,
                "input": tool_input,
            }
        ],
        "stop_reason": "tool_use",
        "model": "mock",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_simple_text_response() -> None:
    """When the provider returns plain text, chat() returns it directly."""
    provider = MockProvider([_text_response("The market looks stable.")])
    memory = AgentMemory(db_url="sqlite://")
    ctx = AgentContext()

    brain = AgentBrain(
        provider=provider,
        tools=_DUMMY_TOOLS,
        context=ctx,
        memory=memory,
        system_prompt="You are a test agent.",
    )

    result = await brain.chat("How is the market?")
    assert result == "The market looks stable."

    # Memory should have both user and assistant messages.
    msgs = memory.get_messages()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_chat_with_tool_call() -> None:
    """When the provider calls a tool, the brain executes it and continues."""
    call_log: list[tuple[str, dict]] = []

    async def fake_handler(name: str, args: dict[str, Any]) -> str:
        call_log.append((name, args))
        return '{"price": 150.0}'

    provider = MockProvider(
        [
            _tool_call_response("get_price", {"symbol": "AAPL"}),
            _text_response("AAPL is at $150."),
        ]
    )
    memory = AgentMemory(db_url="sqlite://")
    ctx = AgentContext(tool_handlers={"get_price": fake_handler})

    brain = AgentBrain(
        provider=provider,
        tools=_DUMMY_TOOLS,
        context=ctx,
        memory=memory,
    )

    result = await brain.chat("What is AAPL at?")
    assert result == "AAPL is at $150."
    assert len(call_log) == 1
    assert call_log[0] == ("get_price", {"symbol": "AAPL"})


@pytest.mark.asyncio
async def test_chat_unknown_tool_returns_error_result() -> None:
    """When the provider calls an unknown tool, the brain returns an error result
    and continues to a final text response."""
    provider = MockProvider(
        [
            _tool_call_response("nonexistent_tool", {}),
            _text_response("Sorry, something went wrong."),
        ]
    )
    memory = AgentMemory(db_url="sqlite://")
    ctx = AgentContext()  # no handlers registered

    brain = AgentBrain(
        provider=provider,
        tools=_DUMMY_TOOLS,
        context=ctx,
        memory=memory,
    )

    result = await brain.chat("Do something impossible")
    assert result == "Sorry, something went wrong."
