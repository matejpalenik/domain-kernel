"""Caller-owned or unpooled PostgreSQL resources with explicit schema management."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, ClassVar, final, override

from sqlalchemy import insert, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema

from domain_kernel.shared.application.persistence import UnitOfWorkFactory
from domain_kernel.shared.errors import CodedDomainError, MissingCapabilityError
from domain_kernel.shared.infrastructure.sqlite import (
    SCHEMA_VERSION,
    DatabaseSchemaError,
    SchemaRow,
    SQLiteTransaction,
    finish,
    open_operation,
)
from domain_kernel.shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy import Connection
    from sqlalchemy.ext.asyncio import AsyncConnection

    from domain_kernel.shared.application.persistence import Clock


_MAX_IDENTIFIER_BYTES = 63


@dataclass(frozen=True, kw_only=True)
class PostgreSQLSettings:
    """Exact operator-selected database URL, namespace, and operation limit."""

    dsn: str = field(repr=False)
    schema: str = "domain_kernel"
    concurrency: int = 4

    def __post_init__(self) -> None:
        """Capture settings without loading the driver or connecting to the server."""
        TextValidation.require_text(value=self.dsn, field="PostgreSQL DSN")
        TextValidation.require_text(value=self.schema, field="PostgreSQL schema")
        if "\x00" in self.schema or len(self.schema.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
            raise ValueError("Use a PostgreSQL schema name of at most 63 bytes")
        if type(self.concurrency) is not int or self.concurrency < 1:
            raise ValueError("Set positive PostgreSQL operation concurrency")


class DatabaseOperationError(CodedDomainError):
    """PostgreSQL could not complete an operation or establish its outcome."""

    _error_code: ClassVar[str] = "database_operation"


def _engine(*, settings: PostgreSQLSettings) -> AsyncEngine:
    try:
        url = make_url(name_or_url=settings.dsn)
        if url.drivername in ("postgres", "postgresql", "postgresql+psycopg"):
            return create_async_engine(
                url.set(drivername="postgresql+psycopg"),
                poolclass=NullPool,
                hide_parameters=True,
            )
    except ModuleNotFoundError:
        raise MissingCapabilityError(message="Install the Domain Kernel postgres extra.") from None
    except (SQLAlchemyError, ValueError, TypeError):
        pass
    raise DatabaseSchemaError(message="Supply a valid PostgreSQL connection URI.")


def _scope(*, engine: AsyncEngine, settings: PostgreSQLSettings) -> AsyncEngine:
    if engine.dialect.name != "postgresql" or engine.dialect.driver != "psycopg":
        raise DatabaseSchemaError(message="Supply an async SQLAlchemy Psycopg engine.")
    return engine.execution_options(schema_translate_map={None: settings.schema})


def _tables(connection: Connection, *, schema: str) -> set[str]:
    return set(inspect(connection).get_table_names(schema=schema))


async def _initialize_namespace(*, connection: AsyncConnection, schema: str) -> None:
    # Transaction-scoped startup lock coordinates independent operators for one namespace.
    identity = int.from_bytes(sha256(schema.encode()).digest()[:8], byteorder="big", signed=True)
    _ = await connection.execute(
        text("SELECT pg_catalog.pg_advisory_xact_lock(:namespace)"), {"namespace": identity}
    )
    _ = await connection.execute(CreateSchema(name=schema, if_not_exists=True))


async def prepare_postgresql(
    *, engine: AsyncEngine, settings: PostgreSQLSettings, initialize: bool
) -> None:
    """Create the namespace only during explicit setup, or confirm its exact version."""
    try:
        async with engine.begin() as connection:
            if initialize:
                await _initialize_namespace(connection=connection, schema=settings.schema)
            actual = await connection.run_sync(_tables, schema=settings.schema)
            expected = set(SQLiteBase.metadata.tables)
            if initialize and not actual:
                await connection.run_sync(SQLiteBase.metadata.create_all)
                _ = await connection.execute(insert(SchemaRow).values(id=1, version=SCHEMA_VERSION))
                return
            if actual == expected:
                versions = await connection.execute(select(SchemaRow.id, SchemaRow.version))
                if versions.all() == [(1, SCHEMA_VERSION)]:
                    return
    except SQLAlchemyError:
        pass
    raise DatabaseSchemaError(
        message="Check access to the selected PostgreSQL schema and initialize it explicitly."
    )


async def manage_postgresql_schema(
    *, settings: PostgreSQLSettings, initialize: bool, engine: AsyncEngine | None
) -> None:
    """Borrow a host pool or own a temporary setup engine."""
    owned = engine is None
    source = _engine(settings=settings) if engine is None else engine
    try:
        await finish(
            prepare_postgresql(
                engine=_scope(engine=source, settings=settings),
                settings=settings,
                initialize=initialize,
            )
        )
    finally:
        if owned:
            await finish(source.dispose())


@final
class PostgreSQLUnitOfWorkFactory(UnitOfWorkFactory[SQLiteTransaction]):
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
        self._clock = _utc_now if clock is None else clock
        self._host = engine
        self._slots = asyncio.Semaphore(settings.concurrency)

    @override
    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[SQLiteTransaction]:
        async with self._slots:
            source = _engine(settings=self._settings) if self._host is None else self._host
            try:
                scoped = _scope(engine=source, settings=self._settings)
                await finish(
                    prepare_postgresql(engine=scoped, settings=self._settings, initialize=False)
                )
                async with open_operation(engine=scoped, clock=self._clock) as transaction:
                    yield transaction
            except SQLAlchemyError:
                raise DatabaseOperationError(
                    message="Reconnect to PostgreSQL and retry with the same idempotency key.",
                    retryable=True,
                ) from None
            finally:
                if self._host is None:
                    await finish(source.dispose())


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
