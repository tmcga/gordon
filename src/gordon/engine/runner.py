"""Engine runner with graceful shutdown via OS signals."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from gordon.engine.live import LiveEngine
    from gordon.engine.paper import PaperEngine

logger = structlog.get_logger()


class EngineRunner:
    """Manages engine lifecycle with signal handling.

    Handles SIGINT/SIGTERM for graceful shutdown.  Blocks the calling
    thread until the engine finishes or a termination signal arrives.
    """

    def __init__(self, engine: PaperEngine | LiveEngine) -> None:
        self._engine = engine

    def run(self) -> None:
        """Run the engine with signal handling. Blocks until stopped."""
        asyncio.run(self._run_with_signals())

    async def _run_with_signals(self) -> None:
        """Set up signal handlers and await the engine."""
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _request_stop(sig_name: str) -> None:
            logger.info("shutdown_signal", signal=sig_name)
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                _request_stop,
                sig.name,
            )

        engine_task = asyncio.create_task(self._engine.run())
        monitor_task = asyncio.create_task(stop_event.wait())

        # Wait for either the engine to finish naturally or a
        # shutdown signal to arrive.
        done, _pending = await asyncio.wait(
            {engine_task, monitor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if monitor_task in done:
            # Signal received -- tell the engine to stop
            logger.info("engine_runner_stopping")
            await self._engine.stop()
            # Give the engine time to close positions and clean up
            try:
                await asyncio.wait_for(engine_task, timeout=30.0)
            except TimeoutError:
                logger.warning("engine_shutdown_timeout")
                engine_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await engine_task
        else:
            # Engine finished on its own
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task

        # Re-raise any exception from the engine task
        if engine_task.done() and not engine_task.cancelled():
            exc = engine_task.exception()
            if exc is not None:
                raise exc

        logger.info("engine_runner_exited")
