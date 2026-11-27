"""Configure SQLite connections and manage the workspace schema."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, final

from sqlalchemy import (
    URL,
    Connection,
    String,
    column,
    event,
    insert,
    select,
    table,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from domain_kernel.shared.infrastructure.persistence.schema_metadata import SchemaMetadata

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry


from domain_kernel.shared.infrastructure.persistence.database_schema_error import (
    DatabaseSchemaError,
)
from domain_kernel.shared.infrastructure.persistence.schema_row import SchemaRow
from domain_kernel.shared.infrastructure.persistence.schema_version import SCHEMA_VERSION

_REVIEW_TABLES = frozenset(
    {
        "dk_definition",
        "dk_definition_revision",
        "dk_review_case",
        "dk_review_case_version",
        "dk_decision",
    }
)


@final
class SQLiteDatabase:
    """Configure SQLite engines and manage their workspace schema."""

    @staticmethod
    def create_engine(
        *, path: Path, timeout: float, create: bool, exclusive_schema: bool = False
    ) -> AsyncEngine:
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
            """Enable foreign keys on every newly connected SQLite database."""
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
            finally:
                cursor.close()

        @event.listens_for(engine.sync_engine, "begin")
        def begin_sqlite(connection: Connection) -> None:
            """Select the appropriate locking mode for schema setup or an ordinary operation."""
            # The setup engine takes the write lock before inspecting SQLite's catalog.
            _ = connection.exec_driver_sql(
                "BEGIN IMMEDIATE" if create or exclusive_schema else "BEGIN"
            )

        return engine

    @staticmethod
    def _expected_schema(*, connection: AsyncConnection) -> dict[str, str]:
        """Compile the expected table and index definitions for this SQLite dialect."""
        schema: dict[str, str] = {}

        for mapped_table in SchemaMetadata.workspace().sorted_tables:
            schema[mapped_table.name] = str(
                CreateTable(mapped_table).compile(dialect=connection.dialect)
            ).strip()

            for index in mapped_table.indexes:
                if index.name is None:
                    raise RuntimeError("Domain Kernel indexes must have a name")
                schema[index.name] = str(
                    CreateIndex(index).compile(dialect=connection.dialect)
                ).strip()

        return schema

    @staticmethod
    async def _read_schema(*, connection: AsyncConnection) -> dict[str, str]:
        """Read the normalized table and index definitions from SQLite's catalog."""
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

    @staticmethod
    async def _check_schema(*, connection: AsyncConnection, discovered: Mapping[str, str]) -> None:
        """Require the exact known schema and stored version before opening a workspace."""
        if discovered != SQLiteDatabase._expected_schema(connection=connection):
            raise DatabaseSchemaError(
                message="The selected file lacks a compatible Domain Kernel schema"
            )

        versions = await connection.execute(select(SchemaRow.id, SchemaRow.version))
        if versions.all() != [(1, SCHEMA_VERSION)]:
            raise DatabaseSchemaError(
                message="The selected file lacks a compatible Domain Kernel schema version"
            )

    @staticmethod
    async def prepare_schema(*, engine: AsyncEngine, initialize: bool) -> None:
        """Verify the exact SQLite schema, creating it only in an empty file when allowed."""
        try:
            async with engine.begin() as connection:
                discovered = await SQLiteDatabase._read_schema(connection=connection)
                if initialize and not discovered:
                    await connection.run_sync(SchemaMetadata.workspace().create_all)
                    _ = await connection.execute(
                        insert(SchemaRow).values(id=1, version=SCHEMA_VERSION),
                    )

                    return

                await SQLiteDatabase._check_schema(connection=connection, discovered=discovered)
        except SQLAlchemyError:
            raise DatabaseSchemaError(
                message=(
                    "Could not open a compatible SQLite database. "
                    "Check access and initialize the configured path if needed."
                ),
            ) from None

    @staticmethod
    async def upgrade_schema(*, engine: AsyncEngine, target_version: str) -> None:
        """Add the supported missing tables after an explicit upgrade request."""
        if target_version != SCHEMA_VERSION:
            raise DatabaseSchemaError(message="Select the schema version supported by this SDK")

        try:
            async with engine.begin() as connection:
                discovered = await SQLiteDatabase._read_schema(connection=connection)
                expected = SQLiteDatabase._expected_schema(connection=connection)
                if discovered == expected:
                    await SQLiteDatabase._check_schema(connection=connection, discovered=discovered)
                    return

                versions = (await connection.execute(select(SchemaRow.id, SchemaRow.version))).all()

                snapshot_tables = frozenset({"dk_candidate", "dk_validation_report"})
                release_tables = frozenset({"dk_publication", "dk_bundle"})
                pack_tables = frozenset({"dk_model_pack_selection"})
                discovery = frozenset({"dk_discovery_run"})
                alignments = discovery | frozenset(
                    {"dk_reconciliation", "dk_review_case_discovery"}
                )
                extraction = alignments | frozenset({"dk_extraction"})
                excerpts = extraction | frozenset({"dk_source_excerpt"})
                documents = excerpts | frozenset({"dk_source_document"})
                parsed_tables = documents | frozenset(
                    {"dk_source_evidence", "dk_source_parsed_payload"}
                )
                source_tables = parsed_tables | frozenset(
                    {
                        "dk_source",
                        "dk_source_revision",
                        "dk_source_ingestion",
                        "dk_source_manifest",
                        "dk_source_manifest_entry",
                        "dk_source_copy_intent",
                    }
                )
                baseline_tables = frozenset({"dk_model_baseline"}) | source_tables
                dependency_tables = frozenset({"dk_model_dependency"}) | baseline_tables
                legacy = {
                    "1": _REVIEW_TABLES
                    | snapshot_tables
                    | release_tables
                    | pack_tables
                    | dependency_tables,
                    "2": snapshot_tables | release_tables | pack_tables | dependency_tables,
                    "3": release_tables | pack_tables | dependency_tables,
                    "4": pack_tables | dependency_tables,
                    "5": dependency_tables,
                    "6": baseline_tables,
                    "7": source_tables,
                    "8": parsed_tables,
                    "9": documents,
                    "10": excerpts,
                    "11": extraction,
                    "12": alignments,
                    "13": discovery,
                }

                if not any(
                    versions == [(1, version)]
                    and discovered
                    == {name: sql for name, sql in expected.items() if name not in added}
                    for version, added in legacy.items()
                ):
                    raise DatabaseSchemaError(
                        message="The selected file has no supported upgrade path"
                    )

                await connection.run_sync(SchemaMetadata.workspace().create_all)
                _ = await connection.execute(
                    update(SchemaRow).where(SchemaRow.id == 1).values(version=target_version),
                )
        except SQLAlchemyError:
            raise DatabaseSchemaError(
                message="Check access to the selected database before upgrading"
            ) from None
