"""Read exact descriptive-process revisions through the public workspace API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    Activity,
    Client,
    ClientIntegrations,
    DefinitionNotFoundError,
    DomainModelBuilder,
    Event,
    EventKind,
    Flow,
    MissingCapabilityError,
    ModelKind,
    Process,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from contextlib import AbstractAsyncContextManager

    from domain_kernel.modeling.application.protocols.model_catalog import ModelCatalog
    from domain_kernel.projects.application.protocols.project_catalog import ProjectCatalog
    from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
    from domain_kernel.shared.application.protocols.catalog_transaction import CatalogTransaction
    from domain_kernel.shared.application.protocols.idempotency_repository import (
        IdempotencyRepository,
    )
    from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager
    from domain_kernel.shared.application.protocols.workspace_revisions import WorkspaceRevisions
    from tests.support.persistence.database_backend import DatabaseBackend


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("host_managed", [False, True], ids=["built-in", "host-managed"])
async def test_process_lookup_reopens_current_and_historical_revisions(
    database_backend: DatabaseBackend, *, host_managed: bool
) -> None:
    config = database_backend.config
    backend = database_backend.factory()

    @asynccontextmanager
    async def host_transactions() -> AsyncGenerator[CatalogTransaction]:
        async with backend() as transaction:
            yield transaction

    project = await Client(config=config).create_project(actor="author", name="catalog")
    model = await project.create_model(
        actor="author", name="observed", kind=ModelKind.OBSERVED, description="Catalog review."
    )
    start = Event(name="received", kind=EventKind.START)
    activity = Activity(name="check-entry")
    end = Event(name="checked", kind=EventKind.END)
    builder = DomainModelBuilder(model_info=model.info)
    process_id = builder.add_process(
        name="entry-review",
        meaning="Describe entry review.",
        roles=[],
        events=[start, end],
        activities=[activity],
        flows=[
            Flow(name="begin", source=start, target=activity),
            Flow(name="finish", source=activity, target=end),
        ],
    )
    plan = builder.build_change_plan(reason="Describe the current review.")
    proposal = await model.propose_change_plan(actor="author", plan=plan)
    accept = Accept(reason="Agreed.")
    _ = await model.decide_review(actor="reviewer", case=proposal, decision=accept)
    original = await model.get_process(process_id=process_id)
    revision = await model.propose_definition_revision(
        actor="author",
        definition_id=process_id,
        expected_revision=original.revision,
        display_name=original.display_name,
        meaning="Describe review of a submitted catalog entry.",
        body=original.body,
        reason="Clarify which entries are in scope.",
    )
    _ = await model.decide_review(actor="reviewer", case=revision, decision=accept)

    integrations = ClientIntegrations(transactions=host_transactions) if host_managed else None
    reopened = await Client(config=config, integrations=integrations).get_project(name="catalog")
    loaded = await reopened.get_model(name="observed")
    current = await loaded.get_definition(name="entry-review")
    assert isinstance(current, Process)
    assert current.revision == original.revision + 1
    assert current.meaning != original.meaning
    assert current.get_activity(activity_id=activity.id) == activity
    assert await loaded.get_process(process_id=process_id) == current
    assert await loaded.get_process(name="entry-review", revision=original.revision) == original
    with pytest.raises(DefinitionNotFoundError):
        _ = await loaded.get_process(process_id=process_id, revision=current.revision + 1)


@dataclass(frozen=True, kw_only=True)
class _CatalogOnly:
    """Supply catalog capabilities without advertising Review support."""

    projects: ProjectCatalog
    models: ModelCatalog
    operations: IdempotencyRepository
    audit: AuditRepository
    revisions: WorkspaceRevisions
    manager: TransactionManager

    def begin(self) -> AbstractAsyncContextManager[None]:
        return self.manager.begin()


async def test_catalog_only_host_checks_definition_arguments_before_acquiring_resources(
    database_backend: DatabaseBackend,
) -> None:
    backend = database_backend.factory()
    acquisitions = 0

    @asynccontextmanager
    async def host_transactions() -> AsyncGenerator[CatalogTransaction]:
        nonlocal acquisitions
        acquisitions += 1
        async with backend() as transaction:
            yield _CatalogOnly(
                projects=transaction.projects,
                models=transaction.models,
                operations=transaction.operations,
                audit=transaction.audit,
                revisions=transaction.revisions,
                manager=transaction,
            )

    client = Client(
        config=database_backend.config,
        integrations=ClientIntegrations(transactions=host_transactions),
    )
    project = await client.create_project(actor="author", name="catalog")
    model = await project.create_model(
        actor="author", name="observed", kind=ModelKind.OBSERVED, description="Catalog review."
    )
    before_lookup = acquisitions
    with pytest.raises(ValueError, match="exactly one definition name or ID"):
        _ = await model.get_process()
    with pytest.raises(TypeError, match="Definition revision"):
        _ = await model.get_definition(name="entry-review", revision=True)
    assert acquisitions == before_lookup
    with pytest.raises(MissingCapabilityError, match="Configure persistence with manual review"):
        _ = await model.get_process(name="entry-review")
    assert acquisitions == before_lookup + 1
