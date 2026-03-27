"""Agent brain -- the perceive -> reason -> act orchestrator."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from gordon.agent.memory import AgentMemory
    from gordon.agent.providers import AIProvider

log = structlog.get_logger(__name__)

# Type alias for an async tool handler: name -> input dict -> result string.
ToolHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, str]]


@dataclass
class AgentContext:
    """Runtime context passed to the agent brain.

    Holds tool handlers and any ambient state the tools may need.
    """

    tool_handlers: dict[str, ToolHandler] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentBrain:
    """Orchestrates the AI agent: perceive -> reason -> act.

    Uses an ``AIProvider`` with ``tool_use`` for structured decision
    making about market analysis and trading.
    """

    MAX_TOOL_ROUNDS: int = 25  # safety limit

    def __init__(
        self,
        provider: AIProvider,
        tools: list[dict[str, Any]],
        context: AgentContext,
        memory: AgentMemory,
        system_prompt: str = "",
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._context = context
        self._memory = memory
        self._system_prompt = system_prompt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(self, user_message: str) -> str:
        """Process a user message and return the agent's response.

        1. Add user message to memory
        2. Build messages list from memory
        3. Call Claude with tools
        4. Handle tool_use responses (execute tools, feed results back)
        5. Return final text response
        """
        self._memory.add_message("user", user_message)
        messages = self._memory.get_messages()

        for _round in range(self.MAX_TOOL_ROUNDS):
            response = await self._provider.create_message(
                messages=messages,
                system=self._system_prompt,
                tools=self._tools,
            )

            # Check whether Claude wants to call tools.
            tool_use_blocks = [b for b in response["content"] if b["type"] == "tool_use"]

            if not tool_use_blocks:
                # No tool calls -- extract final text and return.
                return self._finalise(response, messages)

            # Append the assistant turn (which contains tool_use blocks).
            messages.append({"role": "assistant", "content": response["content"]})

            # Execute every tool call and collect results.
            tool_results = await self._handle_tool_calls(tool_use_blocks)

            # Feed results back as a single user message with tool_result blocks.
            messages.append({"role": "user", "content": tool_results})  # type: ignore[dict-item]

        # Exhausted rounds -- ask the model to wrap up.
        log.warning("agent_brain.max_tool_rounds_reached", rounds=self.MAX_TOOL_ROUNDS)
        messages.append(
            {
                "role": "user",
                "content": (
                    "You have reached the maximum number of tool calls. "
                    "Please provide your final answer now."
                ),
            }
        )
        response = await self._provider.create_message(
            messages=messages,
            system=self._system_prompt,
            tools=self._tools,
        )
        return self._finalise(response, messages)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _handle_tool_calls(
        self,
        tool_use_blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Execute tool calls and return ``tool_result`` content blocks."""
        results: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            name = block["name"]
            tool_input = block["input"]
            tool_use_id = block["id"]

            handler = self._context.tool_handlers.get(name)
            if handler is None:
                error_msg = f"Unknown tool: {name}"
                log.error("agent_brain.unknown_tool", tool=name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": error_msg,
                        "is_error": True,
                    }
                )
                continue

            try:
                output = await handler(name, tool_input)
                log.info("agent_brain.tool_executed", tool=name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": output,
                    }
                )
            except Exception:
                log.exception("agent_brain.tool_error", tool=name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": f"Tool '{name}' failed with an internal error.",
                        "is_error": True,
                    }
                )

        return results

    def _finalise(
        self,
        response: dict[str, Any],
        messages: list[dict[str, str | Any]],
    ) -> str:
        """Extract text from the final response and persist to memory."""
        text_parts = [b["text"] for b in response["content"] if b["type"] == "text"]
        text = "\n".join(text_parts) if text_parts else ""
        self._memory.add_message("assistant", text)
        return text


__all__ = ["AgentBrain", "AgentContext", "ToolHandler"]
