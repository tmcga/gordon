"""Claude AI provider via the Anthropic SDK."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import structlog
from anthropic import Anthropic

log = structlog.get_logger(__name__)


class AnthropicProvider:
    """Claude AI provider via the Anthropic SDK.

    Wraps the synchronous ``anthropic.Anthropic`` client, exposing an
    async ``create_message`` that is compatible with the ``AIProvider``
    protocol.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._client = Anthropic(api_key=api_key)  # reads ANTHROPIC_API_KEY by default
        log.info("anthropic_provider.initialized", model=model)

    async def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a message to Claude with tools and return the response dict.

        Returns a dict with keys: ``content`` (list of blocks),
        ``stop_reason``, ``model``, ``usage``.

        Each content block is either
        ``{"type": "text", "text": "..."}`` or
        ``{"type": "tool_use", "id": "...", "name": "...", "input": {...}}``.
        """
        loop = asyncio.get_running_loop()

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await loop.run_in_executor(
            None,
            partial(self._client.messages.create, **kwargs),
        )

        # Convert the SDK response object to a plain dict.
        content_blocks: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        result: dict[str, Any] = {
            "content": content_blocks,
            "stop_reason": response.stop_reason,
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
        log.debug(
            "anthropic_provider.response",
            stop_reason=response.stop_reason,
            usage=result["usage"],
        )
        return result


__all__ = ["AnthropicProvider"]
