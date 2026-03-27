"""Typed async event dispatcher."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

    from gordon.core.events import Event

logger = structlog.get_logger()


class EventBus:
    """Dispatch events to registered handlers by event type."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: Callable[..., Any]) -> None:
        """Register a handler for an event type."""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[Event], handler: Callable[..., Any]) -> None:
        """Remove a handler."""
        with contextlib.suppress(ValueError):
            self._handlers[event_type].remove(handler)

    async def emit(self, event: Event) -> None:
        """Dispatch event to all registered handlers for its type."""
        event_type = type(event)
        handlers = list(self._handlers.get(event_type, []))
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    result = handler(event)
                    if asyncio.isfuture(result) or asyncio.iscoroutine(result):
                        await result
            except Exception:
                logger.exception(
                    "event_handler_error",
                    handler=getattr(handler, "__name__", repr(handler)),
                    event_type=event_type.__name__,
                )

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
