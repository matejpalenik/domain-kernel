"""File-backed conformance tests for the built-in SQLite provider."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import InvalidRequestError

from domain_kernel._database import (
    DatabaseSchemaError,
    SchemaManager,
    SQLiteSettings,
    SQLiteUnitOfWorkFactory,
)
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy import Connection, Engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_default_bootstrap_is_lazy_and_concurrent(tmp_path: Path) -> None:
    path = tmp_path / "workspace" / "state.sqlite3"
    settings = SQLiteSettings(path=path, initialize_on_first_use=True)
    factories = [SQLiteUnitOfWorkFactory(settings=settings) for _ in range(6)]

    assert not path.parent.exists()

    async def open_workspace(*, factory: SQLiteUnitOfWorkFactory) -> None:
        async with factory() as transaction, transaction.begin():
            with pytest.raises(RuntimeError, match="already active"):
                async with transaction.begin():
                    pytest.fail("A nested transaction must never be entered")

    _ = await asyncio.gather(*(open_workspace(factory=factory) for factory in factories))
    assert path.is_file()
    await open_workspace(factory=SQLiteUnitOfWorkFactory(settings=settings))


async def test_explicit_path_needs_operator_initialization(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    settings = SQLiteSettings(path=path)
    factory = SQLiteUnitOfWorkFactory(settings=settings)

    with pytest.raises(DatabaseSchemaError, match="initialize"):
        async with factory():
            pytest.fail("An explicit database requires operator setup")

    assert not path.exists()
    await SchemaManager(settings=settings).initialize()
    async with factory(), factory():
        assert path.is_file()


async def test_bootstrap_preserves_unrelated_databases(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    with closing(sqlite3.connect(database=path)) as connection, connection:
        _ = connection.execute("CREATE TABLE host_data (value TEXT)")
        _ = connection.execute("INSERT INTO host_data VALUES ('keep')")
    before = path.read_bytes()
    factory = SQLiteUnitOfWorkFactory(
        settings=SQLiteSettings(path=path, initialize_on_first_use=True),
    )

    with pytest.raises(DatabaseSchemaError, match="compatible"):
        async with factory():
            pytest.fail("An unrelated database must not be opened as a workspace")

    assert path.read_bytes() == before


async def test_bootstrap_does_not_replace_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    contents = b"This is a host file"
    _ = path.write_bytes(contents)

    with pytest.raises(DatabaseSchemaError, match="compatible"):
        await SchemaManager(settings=SQLiteSettings(path=path)).initialize()

    assert path.read_bytes() == contents


async def test_bootstrap_serializes_independent_processes(tmp_path: Path) -> None:
    path = tmp_path / "separate-processes" / "state.sqlite3"
    script = """
import asyncio
import sys
from pathlib import Path
from domain_kernel._database import SQLiteSettings, SQLiteUnitOfWorkFactory

async def run():
    settings = SQLiteSettings(path=Path(sys.argv[1]), initialize_on_first_use=True)
    async with SQLiteUnitOfWorkFactory(settings=settings)():
        pass

asyncio.run(run())
"""

    async def run_client() -> None:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(path),
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, error = await child.communicate()
            assert child.returncode == 0, error.decode()
        finally:
            if child.returncode is None:
                child.kill()
                _ = await child.wait()

    async with asyncio.timeout(15):
        _ = await asyncio.gather(*(run_client() for _ in range(4)))
    assert path.is_file()


async def test_compatible_path_must_retain_its_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    settings = SQLiteSettings(path=path, initialize_on_first_use=True)
    manager = SchemaManager(settings=settings)
    await manager.initialize()
    with closing(sqlite3.connect(database=path)) as connection, connection:
        _ = connection.execute("UPDATE dk_schema SET version = 'future'")
    before = path.read_bytes()

    with pytest.raises(DatabaseSchemaError, match="schema version"):
        await manager.initialize()

    assert path.read_bytes() == before


async def test_operation_slots_release_after_cancellation(tmp_path: Path) -> None:
    settings = SQLiteSettings(
        path=tmp_path / "state.sqlite3",
        concurrency=1,
        initialize_on_first_use=True,
    )
    factory = SQLiteUnitOfWorkFactory(settings=settings)
    started = asyncio.Event()
    entered = asyncio.Event()

    async def pending_operation() -> None:
        started.set()
        async with factory():
            entered.set()

    async with asyncio.timeout(5):
        async with factory() as expired:
            waiting = asyncio.create_task(pending_operation())
            _ = await started.wait()
            assert not entered.is_set()
            _ = waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        async with factory():
            pass

    async def reuse_closed_resource() -> None:
        async with expired.begin():
            pytest.fail("An operation cannot reopen its released session")

    with pytest.raises(InvalidRequestError, match="permanently closed"):
        await reuse_closed_resource()


async def test_failed_schema_creation_rolls_back_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.sqlite3"
    settings = SQLiteSettings(path=path, initialize_on_first_use=True)
    create_all = SQLiteBase.metadata.create_all

    def create_then_fail(bind: Engine | Connection) -> None:
        create_all(bind=bind)
        raise RuntimeError("injected bootstrap failure")

    with monkeypatch.context() as replacement:
        replacement.setattr(SQLiteBase.metadata, "create_all", create_then_fail)
        with pytest.raises(RuntimeError, match="injected bootstrap failure"):
            await SchemaManager(settings=settings).initialize()

    with closing(sqlite3.connect(database=path)) as connection:
        tables = connection.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
        assert not tables
    async with SQLiteUnitOfWorkFactory(settings=settings)():
        pass
