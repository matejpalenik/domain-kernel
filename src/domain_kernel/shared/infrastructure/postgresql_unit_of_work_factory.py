from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from sqlalchemy.exc import SQLAlchemyError

from domain_kernel.shared.application.protocols.unit_of_work_factory import UnitOfWorkFactory
from domain_kernel.shared.infrastructure.persistence.database_completion import DatabaseCompletion
from domain_kernel.shared.infrastructure.persistence.operation_session import OperationSession
from domain_kernel.shared.infrastructure.persistence.sqlalchemy_transaction import (
    SqlAlchemyTransaction,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from domain_kernel.shared.application.idempotency.clock import Clock
    from domain_kernel.shared.infrastructure.postgresql_settings import PostgreSQLSettings

from domain_kernel.shared.infrastructure.database_operation_error import DatabaseOperationError
from domain_kernel.shared.infrastructure.postgresql_database import PostgreSQLDatabase


@final
class PostgreSQLUnitOfWorkFactory(UnitOfWorkFactory[SqlAlchemyTransaction]):
    """Open isolated sessions and release borrowed connections on every exit."""

    def __init__(
        self,
        *,
        settings: PostgreSQLSettings,
        clock: Clock | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        """Capture configuration and the optional caller-owned async engine."""
        self._settings = settings
        self._clock = PostgreSQLUnitOfWorkFactory._utc_now if clock is None else clock
        self._host = engine
        self._slots = asyncio.Semaphore(settings.concurrency)

    @override
    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[SqlAlchemyTransaction]:
        """Open one PostgreSQL session while leaving caller-owned pools available."""
        async with self._slots:
            source = (
                PostgreSQLDatabase.create_engine(settings=self._settings)
                if self._host is None
                else self._host
            )

            try:
                scoped = PostgreSQLDatabase.scope_engine(engine=source, settings=self._settings)
                await DatabaseCompletion.finish(
                    PostgreSQLDatabase.prepare_schema(
                        engine=scoped, settings=self._settings, initialize=False
                    )
                )

                async with OperationSession.open(engine=scoped, clock=self._clock) as transaction:
                    yield transaction
            except SQLAlchemyError:
                raise DatabaseOperationError(
                    message="Reconnect to PostgreSQL and retry with the same idempotency key.",
                    retryable=True,
                ) from None
            finally:
                if self._host is None:
                    await DatabaseCompletion.finish(source.dispose())

    @staticmethod
    def _utc_now() -> datetime:
        """Read the default clock as an aware UTC timestamp."""
        return datetime.now(tz=UTC)
