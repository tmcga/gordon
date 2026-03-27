"""Execution-time helpers for sync and async code."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# @timed decorator
# ---------------------------------------------------------------------------


def timed[F: Callable[..., Any]](fn: F) -> F:
    """Log execution time of a sync or async function via structlog."""

    if asyncio.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                log.info(
                    "function.timed",
                    func=fn.__qualname__,
                    elapsed_s=round(elapsed, 4),
                )

        return _async_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            log.info(
                "function.timed",
                func=fn.__qualname__,
                elapsed_s=round(elapsed, 4),
            )

    return _sync_wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Timer context manager
# ---------------------------------------------------------------------------


class Timer:
    """Context manager that measures wall-clock time.

    Works as both a sync and async context manager::

        with Timer("fetch_prices") as t:
            ...
        print(t.elapsed)

        async with Timer("fetch_prices") as t:
            ...
    """

    def __init__(self, name: str = "block") -> None:
        self.name = name
        self.elapsed: float = 0.0
        self._start: float = 0.0

    # Sync context manager -------------------------------------------------

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed = time.perf_counter() - self._start
        log.info("timer.done", name=self.name, elapsed_s=round(self.elapsed, 4))

    # Async context manager ------------------------------------------------

    async def __aenter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.elapsed = time.perf_counter() - self._start
        log.info("timer.done", name=self.name, elapsed_s=round(self.elapsed, 4))
