"""Tests for gordon.agent.memory -- AgentMemory backed by in-memory SQLite."""

from __future__ import annotations

import pytest

from gordon.agent.memory import AgentMemory


@pytest.fixture()
def memory() -> AgentMemory:
    """Create an in-memory AgentMemory for each test."""
    return AgentMemory(db_url="sqlite://")


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_agent_memory_creation(memory: AgentMemory) -> None:
    # Should start with no messages and no observations.
    assert memory.get_messages() == []
    assert memory.get_observations() == []


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def test_add_and_get_messages(memory: AgentMemory) -> None:
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi there!")

    msgs = memory.get_messages()
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "Hello"}
    assert msgs[1] == {"role": "assistant", "content": "Hi there!"}


def test_get_messages_with_limit(memory: AgentMemory) -> None:
    for i in range(10):
        memory.add_message("user", f"msg-{i}")

    msgs = memory.get_messages(limit=3)
    assert len(msgs) == 3
    # Should be the 3 most recent, in chronological order.
    assert msgs[0]["content"] == "msg-7"
    assert msgs[1]["content"] == "msg-8"
    assert msgs[2]["content"] == "msg-9"


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def test_add_and_get_observations(memory: AgentMemory) -> None:
    memory.add_observation("RSI above 70", context={"symbol": "AAPL", "rsi": 72.5})
    memory.add_observation("Market dip detected")

    obs = memory.get_observations()
    assert len(obs) == 2
    assert obs[0]["observation"] == "RSI above 70"
    assert obs[0]["context"] == {"symbol": "AAPL", "rsi": 72.5}
    assert obs[1]["observation"] == "Market dip detected"
    assert obs[1]["context"] == {}


# ---------------------------------------------------------------------------
# clear_messages keeps observations
# ---------------------------------------------------------------------------


def test_clear_messages_keeps_observations(memory: AgentMemory) -> None:
    memory.add_message("user", "hello")
    memory.add_observation("observation-1")

    memory.clear_messages()

    assert memory.get_messages() == []
    obs = memory.get_observations()
    assert len(obs) == 1
    assert obs[0]["observation"] == "observation-1"


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


def test_close_does_not_error(memory: AgentMemory) -> None:
    memory.add_message("user", "test")
    memory.close()
    # Should not raise.
