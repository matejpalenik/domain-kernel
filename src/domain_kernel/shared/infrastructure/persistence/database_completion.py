"""Finish an owned database operation after cancellation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from collections.abc import Coroutine


@final
class DatabaseCompletion:
    """Retain ownership of database work through caller cancellation."""

    @staticmethod
    async def finish[T](operation: Coroutine[object, object, T], /) -> T:
        """Retain ownership of an in-flight commit or resource cleanup after cancellation."""
        task = asyncio.create_task(operation)

        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    _ = await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:  # noqa: BLE001 - The cancelled caller still receives cancellation.
                    break

            if not task.cancelled():
                _ = task.exception()

            raise
