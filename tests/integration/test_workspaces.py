"""Use the public workspace API against independent SQLite clients."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    AuditAction,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DatabaseInitialization,
    ModelAlreadyExistsError,
    ModelKind,
    ProjectAlreadyExistsError,
)
from domain_kernel._database import (
    DatabaseSchemaError,
    SchemaManager,
    SQLiteSettings,
    SQLiteUnitOfWorkFactory,
)
from domain_kernel.configuration import SQLite

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_same_names_reopen_exact_identities_and_historical_creation(tmp_path: Path) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    client = Client(config=config)
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))
    assert (
        client.inspect_configuration().database_initialization is DatabaseInitialization.AUTOMATIC
    )

    project = await client.create_project(
        actor="demo:author", display_name="Recruitment legislation"
    )
    model = await project.create_model(
        actor="demo:author",
        name="ai-in-recruitment",
        kind=ModelKind.OBSERVED,
        description="Scope the documented recruitment vocabulary.",
    )

    reopened = await Client(config=config).get_project(name="recruitment-legislation")
    reloaded = await reopened.get_model(name="ai-in-recruitment")
    assert reopened.id == project.id
    assert reloaded.scope == model.scope
    assert reloaded.info == model.info
    assert reloaded.info.reference_pack is None
    history = await reopened.get_audit_history()
    assert tuple(event.action for event in history.items) == (
        AuditAction.CREATE_PROJECT,
        AuditAction.CREATE_MODEL,
    )
    model_history = await reloaded.get_audit_history()
    assert model_history.items == history.items[1:]
    assert model_history.items[0].actor == "demo:author"


async def test_duplicate_names_fail_atomically_across_clients(tmp_path: Path) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    first = Client(config=config)
    second = Client(config=config)
    results = await asyncio.gather(
        first.create_project(actor="demo:author", name="recruitment"),
        second.create_project(actor="demo:reviewer", name="recruitment"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ProjectAlreadyExistsError) for result in results) == 1
    project = await first.get_project(name="recruitment")
    assert len((await project.get_audit_history()).items) == 1
    assert len((await first.list_projects()).items) == 1


async def test_explicit_equal_sqlite_configuration_needs_operator_setup(tmp_path: Path) -> None:
    client = Client(config=ClientConfiguration(base_dir=tmp_path, database=SQLite()))
    assert client.inspect_configuration().database_initialization is DatabaseInitialization.EXPLICIT
    with pytest.raises(DatabaseSchemaError, match="initialize"):
        _ = await client.list_projects()
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))


async def test_host_connections_own_setup_and_ignore_implicit_default_path(tmp_path: Path) -> None:
    other = tmp_path / "host" / "workspace.sqlite3"
    host_settings = SQLiteSettings(path=other)
    await SchemaManager(settings=host_settings).initialize()
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path),
        integrations=ClientIntegrations(
            transactions=SQLiteUnitOfWorkFactory(settings=host_settings),
        ),
    )
    assert (
        client.inspect_configuration().database_initialization
        is DatabaseInitialization.HOST_MANAGED
    )
    project = await client.create_project(actor="host:demo", name="host-project")
    assert (await client.get_project(name=project.name)).id == project.id
    assert not await asyncio.to_thread((tmp_path / ".domain-kernel").exists)


async def test_model_names_are_scoped_and_catalog_cursors_bind_the_query(tmp_path: Path) -> None:
    client = Client(config=ClientConfiguration(base_dir=tmp_path))
    first = await client.create_project(actor="editor", name="first")
    second = await client.create_project(actor="editor", name="second")
    for project in (first, second):
        _ = await project.create_model(
            actor="editor",
            name="observed",
            kind=ModelKind.OBSERVED,
            description="Existing scope",
        )
    _ = await first.create_model(
        actor="editor",
        name="proposed",
        kind=ModelKind.PROPOSED,
        description="Next scope",
    )
    with pytest.raises(ModelAlreadyExistsError):
        _ = await first.create_model(
            actor="editor",
            name="observed",
            kind=ModelKind.OBSERVED,
            description="Duplicate",
        )
    page = await first.list_models(limit=1)
    assert tuple(info.name for info in page.items) == ("observed",)
    assert page.next_cursor is not None
    with pytest.raises(ValueError, match="same catalog query"):
        _ = await second.list_models(limit=1, cursor=page.next_cursor)
    following = await first.list_models(limit=1, cursor=page.next_cursor)
    assert tuple(info.name for info in following.items) == ("proposed",)
    assert following.next_cursor is None
    assert tuple(event.action for event in (await first.get_audit_history()).items) == (
        AuditAction.CREATE_PROJECT,
        AuditAction.CREATE_MODEL,
        AuditAction.CREATE_MODEL,
    )
