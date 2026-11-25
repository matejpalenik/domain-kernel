"""Run the same persistence scenarios against disposable backend namespaces."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import DropSchema

from domain_kernel import ClientConfiguration
from domain_kernel._database import (
    PostgreSQLSettings,
    SchemaManager,
    SQLiteSettings,
)
from domain_kernel.configuration import Env, PostgreSQL
from tests.support.persistence.database_backend import DatabaseBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


type _Backend = Literal["sqlite", "postgresql"]


class _Parameter(Protocol):
    @property
    def param(self) -> _Backend: ...


@pytest_asyncio.fixture(params=["sqlite", "postgresql"])
async def database_backend(
    request: _Parameter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[DatabaseBackend]:
    """Allocate a fresh SQLite file or isolated PostgreSQL schema for each scenario."""
    if request.param == "sqlite":
        yield DatabaseBackend(
            config=ClientConfiguration(base_dir=tmp_path),
            settings=SQLiteSettings(
                path=tmp_path / ".domain-kernel/state.sqlite3", initialize_on_first_use=True
            ),
        )
        return
    dsn = os.environ.get("DK_TEST_POSTGRES_DSN")
    if dsn is None:
        pytest.skip("Provide a disposable PostgreSQL DSN for database parity")
    schema = f"dk_test_{uuid4().hex}"
    monkeypatch.setenv("DK_TEST_STATE_DSN", dsn)
    settings = PostgreSQLSettings(dsn=dsn, schema=schema)
    try:
        await SchemaManager(settings=settings).initialize()
        yield DatabaseBackend(
            config=ClientConfiguration(
                base_dir=tmp_path,
                database=PostgreSQL(dsn=Env(env="DK_TEST_STATE_DSN"), schema_name=schema),
            ),
            settings=settings,
        )
    finally:
        engine = create_async_engine(
            make_url(dsn).set(drivername="postgresql+psycopg"),
            poolclass=NullPool,
            hide_parameters=True,
        )
        try:
            async with engine.begin() as connection:
                _ = await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            await engine.dispose()
