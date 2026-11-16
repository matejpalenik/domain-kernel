"""SQLAlchemy resources and schema verification for built-in SQLite workspaces."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, ClassVar, final, override

from sqlalchemy import URL, Connection, Integer, String, column, event, insert, select, table
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from domain_kernel._shared.application.persistence import Transaction
from domain_kernel._shared.infrastructure.sqlite_audit import SQLiteAuditRepository
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel._shared.infrastructure.sqlite_operations import SQLiteIdempotencyRepository
from domain_kernel._shared.infrastructure.sqlite_workspaces import SQLiteWorkspaceRevisions
from domain_kernel.shared.errors import CodedDomainError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Mapping
    from pathlib import Path

    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

    from domain_kernel._shared.application.persistence import (
        AuditRepository,
        Clock,
        IdempotencyRepository,
        WorkspaceRevisions,
    )

_SCHEMA_VERSION = "1"


class DatabaseSchemaError(CodedDomainError):
    """SQLite setup could not find or establish a compatible schema."""

    _error_code: ClassVar[str] = "database_schema"


@final
class _SchemaRow(SQLiteBase):
    __tablename__ = "dk_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String, nullable=False)


def create_engine(*, path: Path, timeout: float, create: bool) -> AsyncEngine:
    """Create an unpooled engine for one SQLite resource scope."""
    mode = "rwc" if create else "rw"
    url = URL.create(
        drivername="sqlite+aiosqlite",
        database=path.as_uri(),
        query={"mode": mode, "uri": "true"},
    )
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "timeout": timeout,
            "isolation_level": None,
            "autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL,
        },
        hide_parameters=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def begin_sqlite(connection: Connection) -> None:
        # The setup engine takes the write lock before inspecting SQLite's catalog.
        _ = connection.exec_driver_sql("BEGIN IMMEDIATE" if create else "BEGIN")

    return engine


def _expected_schema(*, connection: AsyncConnection) -> dict[str, str]:
    schema: dict[str, str] = {}
    for mapped_table in SQLiteBase.metadata.sorted_tables:
        schema[mapped_table.name] = str(
            CreateTable(mapped_table).compile(dialect=connection.dialect)
        ).strip()
        for index in mapped_table.indexes:
            if index.name is None:
                raise RuntimeError("Domain Kernel indexes must have a name")
            schema[index.name] = str(CreateIndex(index).compile(dialect=connection.dialect)).strip()
    return schema


async def _read_schema(*, connection: AsyncConnection) -> dict[str, str]:
    name_column = column("name", String)
    sql_column = column("sql", String)
    catalog = table("sqlite_schema", name_column, sql_column)
    rows = await connection.execute(
        select(name_column, sql_column)
        .select_from(catalog)
        .where(
            ~name_column.bool_op("GLOB")("sqlite_*"),
        ),
    )
    schema: dict[str, str] = {}
    for name, sql in rows:
        if type(name) is not str or type(sql) is not str:
            raise DatabaseSchemaError(message="SQLite catalog entries are invalid")
        schema[name] = sql
    return schema


async def _check_schema(*, connection: AsyncConnection, discovered: Mapping[str, str]) -> None:
    if discovered != _expected_schema(connection=connection):
        raise DatabaseSchemaError(
            message="The selected file lacks a compatible Domain Kernel schema"
        )
    versions = await connection.execute(select(_SchemaRow.id, _SchemaRow.version))
    if versions.all() != [(1, _SCHEMA_VERSION)]:
        raise DatabaseSchemaError(
            message="The selected file lacks a compatible Domain Kernel schema version"
        )


async def prepare_schema(*, engine: AsyncEngine, initialize: bool) -> None:
    """Verify the exact SQLite schema, creating it only in an empty file when allowed."""
    try:
        async with engine.begin() as connection:
            discovered = await _read_schema(connection=connection)
            if initialize and not discovered:
                await connection.run_sync(SQLiteBase.metadata.create_all)
                _ = await connection.execute(
                    insert(_SchemaRow).values(id=1, version=_SCHEMA_VERSION),
                )
                return
            await _check_schema(connection=connection, discovered=discovered)
    except SQLAlchemyError:
        raise DatabaseSchemaError(
            message=(
                "Could not open a compatible SQLite database. "
                "Check access and initialize the configured path if needed."
            ),
        ) from None


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


@final
class SQLiteTransaction(Transaction):
    """Transaction manager backed by one session acquired for the operation."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        """Bind the operation's clean session."""
        self._session = session
        self._operations = SQLiteIdempotencyRepository(session=session, clock=clock)
        self._audit = SQLiteAuditRepository(session=session)
        self._revisions = SQLiteWorkspaceRevisions(session=session)

    @property
    @override
    def audit(self) -> AuditRepository:
        return self._audit

    @property
    @override
    def revisions(self) -> WorkspaceRevisions:
        return self._revisions

    @property
    @override
    def operations(self) -> IdempotencyRepository:
        return self._operations

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        if self._session.in_transaction():
            raise RuntimeError("The database transaction is already active")
        _ = await self._session.begin()
        try:
            yield
            await finish(self._session.commit())
        except BaseException:
            await finish(self._session.rollback())
            raise


@asynccontextmanager
async def open_operation(*, engine: AsyncEngine, clock: Clock) -> AsyncGenerator[SQLiteTransaction]:
    """Bind resources to one session and release them without committing."""
    session = AsyncSession(
        bind=engine,
        expire_on_commit=False,
        autobegin=False,
        close_resets_only=False,
    )
    try:
        yield SQLiteTransaction(session=session, clock=clock)
    finally:
        await finish(session.close())
