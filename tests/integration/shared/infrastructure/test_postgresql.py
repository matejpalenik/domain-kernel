"""Exercise an explicitly initialized PostgreSQL workspace through the public SDK."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DomainModelBundle,
    MissingCapabilityError,
    ModelKind,
    ProjectId,
    ProjectInfo,
    ProjectNotFoundError,
)
from domain_kernel._database import (
    DatabaseSchemaError,
    PostgreSQLSettings,
    PostgreSQLUnitOfWorkFactory,
    SchemaManager,
)
from domain_kernel.configuration import Env, PostgreSQL

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine

    from tests.support.persistence.database_backend import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_explicit_postgres_schema_survives_workspace_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dsn = os.environ.get("DK_TEST_POSTGRES_DSN")
    if dsn is None:
        pytest.skip("Provide a disposable PostgreSQL DSN for the integration test")
    schema = f"dk_test_{uuid4().hex}"
    monkeypatch.setenv("DK_STATE_DSN", dsn)
    configuration = ClientConfiguration(
        base_dir=tmp_path,
        database=PostgreSQL(dsn=Env(env="DK_STATE_DSN"), schema_name=schema),
    )
    client = Client(config=configuration)
    with pytest.raises(DatabaseSchemaError):
        _ = await client.create_project(actor="author", name="recruitment")
    await SchemaManager(settings=PostgreSQLSettings(dsn=dsn, schema=schema)).initialize()
    project = await client.create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author",
        name="formal",
        kind=ModelKind.PROPOSED,
        description="Review recruitment.",
    )
    proposal = await model.propose_definition(
        actor="author",
        name="recruitment-ai-system",
        meaning="A system intended for recruitment.",
        body=ConceptDefinition(),
        reason="Record the reviewed purpose.",
    )
    _ = await model.decide_review(
        actor="reviewer", case=proposal, decision=Accept(reason="Reviewed.")
    )
    prepared = await model.prepare_publication(actor="author", idempotency_key="prepare")
    release = await model.publish(
        actor="publisher",
        publication=prepared,
        version="1.0.0",
        reason="Deliver the reviewed definition.",
        idempotency_key="publish",
    )
    restarted_project = await Client(config=configuration).get_project(name="recruitment")
    restarted = await restarted_project.get_model(name="formal")
    restored = await restarted.get_version(version="1.0.0")
    assert restarted.scope == model.scope
    assert restored == DomainModelBundle.deserialize(payload=release.serialize())
    assert not (tmp_path / ".domain-kernel" / "state.sqlite3").exists()


async def test_sessions_are_isolated_and_nested_transactions_are_rejected(
    database_backend: DatabaseBackend,
) -> None:
    project = ProjectInfo(
        id=ProjectId(value="isolation"),
        name="isolation",
        display_name="Isolated project",
        created_at=datetime.now(tz=UTC),
    )
    factory = database_backend.factory()
    async with factory() as writer, factory() as reader:
        async with writer.begin():
            await writer.projects.create(project=project)
            with pytest.raises(RuntimeError, match="already active"):
                async with writer.begin():
                    pytest.fail("Nested transaction unexpectedly started")
            async with reader.begin():
                with pytest.raises(ProjectNotFoundError):
                    _ = await reader.projects.get(name=project.name)
        async with reader.begin():
            materialized = await reader.projects.get(name=project.name)
    assert materialized == project


async def test_postgres_borrowed_pool_remains_open_after_setup_and_operations(
    database_backend: DatabaseBackend,
) -> None:
    settings = database_backend.settings
    if not isinstance(settings, PostgreSQLSettings):
        pytest.skip("Test the PostgreSQL pool binding")
    engine = create_async_engine(
        make_url(settings.dsn).set(drivername="postgresql+psycopg"),
        pool_size=1,
        max_overflow=0,
        hide_parameters=True,
    )
    original_pool = engine.pool
    try:
        await SchemaManager(settings=settings, engine=engine).initialize()
        factory = PostgreSQLUnitOfWorkFactory(settings=settings, engine=engine)
        async with factory() as transaction, transaction.begin():
            _ = await transaction.projects.list(limit=1, cursor=None)
        assert engine.pool is original_pool
        async with engine.connect() as connection:
            assert (await connection.scalar(text("SELECT 1"))) == 1
    finally:
        await engine.dispose()


async def test_postgres_missing_driver_never_redirects_to_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_options: object) -> AsyncEngine:
        raise ModuleNotFoundError("psycopg")

    monkeypatch.setattr(
        "domain_kernel.shared.infrastructure.postgresql_database.create_async_engine", unavailable
    )
    monkeypatch.setenv("DK_TEST_STATE_DSN", "postgresql://user@127.0.0.1/test")
    client = Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            database=PostgreSQL(dsn=Env(env="DK_TEST_STATE_DSN")),
        )
    )
    with pytest.raises(MissingCapabilityError, match="postgres extra"):
        _ = await client.list_projects()
    assert not (tmp_path / ".domain-kernel").exists()
