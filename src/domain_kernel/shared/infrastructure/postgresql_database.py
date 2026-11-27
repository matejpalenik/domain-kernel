"""Configure the PostgreSQL engine and validate or initialize its schema."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, final

from sqlalchemy import insert, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema

from domain_kernel.shared.errors.missing_capability_error import MissingCapabilityError
from domain_kernel.shared.infrastructure.persistence.database_completion import DatabaseCompletion
from domain_kernel.shared.infrastructure.persistence.database_schema_error import (
    DatabaseSchemaError,
)
from domain_kernel.shared.infrastructure.persistence.schema_metadata import SchemaMetadata
from domain_kernel.shared.infrastructure.persistence.schema_row import SchemaRow
from domain_kernel.shared.infrastructure.persistence.schema_version import SCHEMA_VERSION

if TYPE_CHECKING:
    from sqlalchemy import Connection
    from sqlalchemy.ext.asyncio import AsyncConnection

    from domain_kernel.shared.infrastructure.postgresql_settings import PostgreSQLSettings


@final
class PostgreSQLDatabase:
    """Configure PostgreSQL engines and manage their workspace schema."""

    @staticmethod
    def create_engine(*, settings: PostgreSQLSettings) -> AsyncEngine:
        """Build an async Psycopg engine with operation-local connections."""
        try:
            url = make_url(name_or_url=settings.dsn)
            if url.drivername in ("postgres", "postgresql", "postgresql+psycopg"):
                return create_async_engine(
                    url.set(drivername="postgresql+psycopg"),
                    poolclass=NullPool,
                    hide_parameters=True,
                )
        except ModuleNotFoundError:
            raise MissingCapabilityError(
                message="Install the Domain Kernel postgres extra."
            ) from None
        except (SQLAlchemyError, ValueError, TypeError):
            pass

        raise DatabaseSchemaError(message="Supply a valid PostgreSQL connection URI.")

    @staticmethod
    def scope_engine(*, engine: AsyncEngine, settings: PostgreSQLSettings) -> AsyncEngine:
        """Bind the schema mapping without taking ownership of the supplied engine."""
        if engine.dialect.name != "postgresql" or engine.dialect.driver != "psycopg":
            raise DatabaseSchemaError(message="Supply an async SQLAlchemy Psycopg engine.")

        return engine.execution_options(schema_translate_map={None: settings.schema})

    @staticmethod
    def _tables(connection: Connection, *, schema: str) -> set[str]:
        """List the physical tables present in the selected PostgreSQL schema."""
        return set(inspect(connection).get_table_names(schema=schema))

    @staticmethod
    async def _initialize_namespace(*, connection: AsyncConnection, schema: str) -> None:
        """Create the configured PostgreSQL schema if it does not exist."""
        # Transaction-scoped startup lock coordinates independent operators for one namespace.
        identity = int.from_bytes(
            sha256(schema.encode()).digest()[:8], byteorder="big", signed=True
        )
        _ = await connection.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(:namespace)"), {"namespace": identity}
        )

        _ = await connection.execute(CreateSchema(name=schema, if_not_exists=True))

    @staticmethod
    async def prepare_schema(
        *, engine: AsyncEngine, settings: PostgreSQLSettings, initialize: bool
    ) -> None:
        """Create the namespace only during explicit setup, or confirm its exact version."""
        try:
            async with engine.begin() as connection:
                if initialize:
                    await PostgreSQLDatabase._initialize_namespace(
                        connection=connection, schema=settings.schema
                    )

                actual = await connection.run_sync(
                    PostgreSQLDatabase._tables, schema=settings.schema
                )
                metadata = SchemaMetadata.workspace()
                expected = set(metadata.tables)

                if initialize and not actual:
                    await connection.run_sync(metadata.create_all)
                    _ = await connection.execute(
                        insert(SchemaRow).values(id=1, version=SCHEMA_VERSION)
                    )
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

    @staticmethod
    async def manage_schema(
        *, settings: PostgreSQLSettings, initialize: bool, engine: AsyncEngine | None
    ) -> None:
        """Borrow a host pool or own a temporary setup engine."""
        owned = engine is None
        source = PostgreSQLDatabase.create_engine(settings=settings) if engine is None else engine

        try:
            await DatabaseCompletion.finish(
                PostgreSQLDatabase.prepare_schema(
                    engine=PostgreSQLDatabase.scope_engine(engine=source, settings=settings),
                    settings=settings,
                    initialize=initialize,
                )
            )
        finally:
            if owned:
                await DatabaseCompletion.finish(source.dispose())
