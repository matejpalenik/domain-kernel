"""Coordinate lease renewal during asynchronous application work."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine


@final
class LeaseRenewal:
    """Keep an operation's existing lease active while its work runs."""

    @staticmethod
    async def run[T](
        *,
        work: Coroutine[object, object, T],
        renew: Callable[[], Awaitable[None]],
        interval: float,
    ) -> T:
        """Run work while periodically renewing its lease.

        Run the coroutine in its own task. If it is still pending after the
        interval, await the renewal callback and wait again. The caller
        acquires and releases the lease and controls the renewal transaction.

        If renewal fails or the caller is cancelled, cancel and await the pending
        work task so its coroutine cleanup can run before control returns to the
        caller. Exceptions from the work or renewal propagate to the caller.

        Args:
            work: The coroutine to run under an already acquired lease.
            renew: A callback that extends the current lease when awaited.
            interval: Seconds to wait for work before requesting renewal. Allow
                enough time for the callback to finish before the lease expires.

        Returns:
            The result of the work coroutine.
        """
        child = asyncio.create_task(work)

        try:
            while True:
                done, _ = await asyncio.wait((child,), timeout=interval)
                if done:
                    return child.result()

                await renew()
        finally:
            if not child.done():
                _ = child.cancel()

            _ = await asyncio.gather(child, return_exceptions=True)
