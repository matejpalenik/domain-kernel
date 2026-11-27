"""Own the SQLAlchemy session for a single SDK operation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from domain_kernel.shared.application.idempotency.clock import Clock

from domain_kernel.shared.infrastructure.persistence.database_completion import DatabaseCompletion
from domain_kernel.shared.infrastructure.persistence.sqlalchemy_transaction import (
    SqlAlchemyTransaction,
)


@final
class OperationSession:
    """Own one session for the lifetime of an SDK operation."""

    @staticmethod
    @asynccontextmanager
    async def open(*, engine: AsyncEngine, clock: Clock) -> AsyncGenerator[SqlAlchemyTransaction]:
        """Open a session for one operation and close it on exit.

        The caller owns the engine. The yielded transaction controls commit and rollback.

        Yields:
            Repositories and a transaction manager bound to the same session.
        """
        session = AsyncSession(
            bind=engine,
            expire_on_commit=False,
            autobegin=False,
            close_resets_only=False,
        )

        try:
            yield SqlAlchemyTransaction(session=session, clock=clock)
        finally:
            await DatabaseCompletion.finish(session.close())
