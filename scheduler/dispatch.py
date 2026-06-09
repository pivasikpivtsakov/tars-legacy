import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class DispatchRunner:
    # Single serialized worker: every wake coalesces into one sweep at a time, so
    # an order can never be offered by two concurrent sweeps.
    def __init__(self, *, run: Callable[[], Awaitable[None]]) -> None:
        self._run = run
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def request(self) -> None:
        self._wake.set()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            try:
                await self._run()
            except Exception:
                logger.exception("order dispatch run failed")
