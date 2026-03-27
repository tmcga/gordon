"""AI provider protocol and implementations."""

from __future__ import annotations

from typing import Any, Protocol


class AIProvider(Protocol):
    """Protocol that all AI providers must satisfy."""

    async def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Call the AI model and return the response."""
        ...


__all__ = ["AIProvider"]
