"""Compose the built-in SQLite resources and operator-owned schema setup."""

from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from domain_kernel.shared.application.protocols.unit_of_work_factory import UnitOfWorkFactory
from domain_kernel.shared.infrastructure.persistence.database_completion import DatabaseCompletion
from domain_kernel.shared.infrastructure.persistence.database_schema_error import (
    DatabaseSchemaError,
)
from domain_kernel.shared.infrastructure.persistence.operation_session import OperationSession
from domain_kernel.shared.infrastructure.persistence.schema_version import SCHEMA_VERSION
from domain_kernel.shared.infrastructure.postgresql_database import PostgreSQLDatabase
from domain_kernel.shared.infrastructure.postgresql_settings import PostgreSQLSettings
from domain_kernel.shared.infrastructure.postgresql_unit_of_work_factory import (
    PostgreSQLUnitOfWorkFactory,
)
from domain_kernel.shared.infrastructure.sqlite_database import SQLiteDatabase

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine

    from domain_kernel.shared.application.idempotency.clock import Clock
    from domain_kernel.shared.infrastructure.persistence.sqlalchemy_transaction import (
        SqlAlchemyTransaction,
    )

__all__ = [
    "DatabaseSchemaError",
    "PostgreSQLSettings",
    "PostgreSQLUnitOfWorkFactory",
    "SQLiteSettings",
    "SQLiteUnitOfWorkFactory",
    "SchemaManager",
]


@dataclass(frozen=True, kw_only=True)
class SQLiteSettings:
    """Effective internal SQLite settings selected by composition."""

    path: Path
    initialize_on_first_use: bool = False
    busy_timeout: float = 5.0
    concurrency: int = 4

    def __post_init__(self) -> None:
        """Capture a fixed absolute path and validate resource limits."""
        if type(self.initialize_on_first_use) is not bool:
            raise TypeError("SQLite initialization selection must be a bool")
        if type(self.busy_timeout) not in (int, float) or not math.isfinite(self.busy_timeout):
            raise ValueError("SQLite busy timeout must be a finite number")
        if self.busy_timeout <= 0:
            raise ValueError("SQLite busy timeout must be positive")
        if type(self.concurrency) is not int or self.concurrency < 1:
            raise ValueError("SQLite operation concurrency must be a positive integer")
        object.__setattr__(self, "path", self.path.absolute())


@final
class SchemaManager:
    """Manage the selected database schema on an explicit operator request."""

    def __init__(
        self, *, settings: SQLiteSettings | PostgreSQLSettings, engine: AsyncEngine | None = None
    ) -> None:
        """Retain settings and an optional host-owned PostgreSQL pool."""
        if engine is not None and not isinstance(settings, PostgreSQLSettings):
            raise ValueError("Supply a host engine only for PostgreSQL schema setup")
        self._settings = settings
        self._host = engine

    async def initialize(self) -> None:
        """Create a new schema, or confirm the existing schema can be reused."""
        if isinstance(self._settings, PostgreSQLSettings):
            await PostgreSQLDatabase.manage_schema(
                settings=self._settings, initialize=True, engine=self._host
            )
            return
        try:
            await DatabaseCompletion.finish(
                asyncio.to_thread(self._settings.path.parent.mkdir, parents=True, exist_ok=True)
            )
        except OSError:
            raise DatabaseSchemaError(
                message="Check access to the selected SQLite directory"
            ) from None
        engine = SQLiteDatabase.create_engine(
            path=self._settings.path, timeout=self._settings.busy_timeout, create=True
        )
        try:
            await DatabaseCompletion.finish(
                SQLiteDatabase.prepare_schema(engine=engine, initialize=True)
            )
        finally:
            await DatabaseCompletion.finish(engine.dispose())

    async def upgrade(self, *, target_version: str) -> None:
        """Upgrade the exact selected workspace after an explicit operator request."""
        if isinstance(self._settings, PostgreSQLSettings):
            if target_version != SCHEMA_VERSION:
                raise DatabaseSchemaError(message="Select the schema version supported by this SDK")
            await PostgreSQLDatabase.manage_schema(
                settings=self._settings, initialize=False, engine=self._host
            )
            return
        engine = SQLiteDatabase.create_engine(
            path=self._settings.path,
            timeout=self._settings.busy_timeout,
            create=False,
            exclusive_schema=True,
        )
        try:
            await DatabaseCompletion.finish(
                SQLiteDatabase.upgrade_schema(engine=engine, target_version=target_version)
            )
        finally:
            await DatabaseCompletion.finish(engine.dispose())


@final
class SQLiteUnitOfWorkFactory(UnitOfWorkFactory["SqlAlchemyTransaction"]):
    """Acquire an unpooled operation resource with bounded per-factory concurrency."""

    def __init__(self, *, settings: SQLiteSettings, clock: Clock | None = None) -> None:
        """Capture settings without opening a database or starting background work."""
        self._settings = settings
        self._clock = clock if clock is not None else SQLiteUnitOfWorkFactory._utc_now
        self._slots = asyncio.Semaphore(settings.concurrency)
        self._initialization = asyncio.Lock()
        self._initialized = False

    async def _initialize_default(self) -> None:
        if self._settings.initialize_on_first_use and not self._initialized:
            async with self._initialization:
                if not self._initialized:
                    await SchemaManager(settings=self._settings).initialize()
                    self._initialized = True

    @override
    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[SqlAlchemyTransaction]:
        async with self._slots:
            await self._initialize_default()
            engine = SQLiteDatabase.create_engine(
                path=self._settings.path,
                timeout=self._settings.busy_timeout,
                create=False,
            )
            try:
                await DatabaseCompletion.finish(
                    SQLiteDatabase.prepare_schema(engine=engine, initialize=False)
                )
                async with OperationSession.open(engine=engine, clock=self._clock) as transaction:
                    yield transaction
            finally:
                await DatabaseCompletion.finish(engine.dispose())

    @staticmethod
    def _utc_now() -> datetime:
        """Read the default operation clock as an aware UTC timestamp."""
        return datetime.now(tz=UTC)
