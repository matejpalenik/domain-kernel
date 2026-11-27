from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final, override

from domain_kernel.discovery.application.run_ports import DiscoveryTransaction
from domain_kernel.discovery.infrastructure.sqlite_extraction import SQLiteExtraction
from domain_kernel.discovery.infrastructure.sqlite_runs import SQLiteDiscoveryRuns
from domain_kernel.modeling.application.dependencies import (
    DependencyTransaction,
    PublishedDependencies,
)
from domain_kernel.modeling.application.publication_ports import PublicationTransaction
from domain_kernel.modeling.infrastructure.sqlite_compilation import SQLiteCompilation
from domain_kernel.modeling.infrastructure.sqlite_dependencies import SQLiteDependencyPins
from domain_kernel.modeling.infrastructure.sqlite_publications import SQLitePublications
from domain_kernel.reconciliation.application.ports import ReconciliationTransaction
from domain_kernel.reconciliation.infrastructure.sqlite_reconciliation import SQLiteReconciliation
from domain_kernel.reference_packs.infrastructure.sqlite_selection import SQLiteSelectedPacks
from domain_kernel.review.infrastructure.sqlite_review import SQLiteDefinitions, SQLiteReviews
from domain_kernel.sources.application.ports import SourceTransaction
from domain_kernel.sources.infrastructure.sqlite_sources import SQLiteSources

from .repositories.sqlalchemy_audit_repository import (
    SqlAlchemyAuditRepository,
)
from .repositories.sqlalchemy_idempotency_repository import (
    SqlAlchemyIdempotencyRepository,
)
from .repositories.sqlalchemy_model_catalog import (
    SqlAlchemyModelCatalog,
)
from .repositories.sqlalchemy_project_catalog import (
    SqlAlchemyProjectCatalog,
)
from .repositories.sqlalchemy_workspace_revisions import (
    SqlAlchemyWorkspaceRevisions,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.discovery.application.ports import ExtractionRepository
    from domain_kernel.discovery.application.run_ports import DiscoveryRuns
    from domain_kernel.modeling.application.compilation_ports import CompilationRepository
    from domain_kernel.modeling.application.protocols.model_catalog import ModelCatalog
    from domain_kernel.modeling.application.publication_ports import PublicationRepository
    from domain_kernel.projects.application.protocols.project_catalog import ProjectCatalog
    from domain_kernel.reconciliation.application.ports import ReconciliationRepository
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
    from domain_kernel.review.application.ports import DefinitionRepository, ReviewRepository
    from domain_kernel.shared.application.idempotency.clock import Clock
    from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
    from domain_kernel.shared.application.protocols.idempotency_repository import (
        IdempotencyRepository,
    )
    from domain_kernel.shared.application.protocols.workspace_revisions import WorkspaceRevisions
    from domain_kernel.sources.application.ports import SourceRepository

from domain_kernel.shared.infrastructure.persistence.database_completion import DatabaseCompletion


@final
class SqlAlchemyTransaction(
    PublicationTransaction,
    DependencyTransaction,
    SourceTransaction,
    ReconciliationTransaction,
    DiscoveryTransaction,
):
    """Transaction manager backed by one session acquired for the operation."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        """Bind the operation's clean session."""
        self._session = session
        self._operations = SqlAlchemyIdempotencyRepository(session=session, clock=clock)
        self._audit = SqlAlchemyAuditRepository(session=session)
        self._revisions = SqlAlchemyWorkspaceRevisions(session=session)

        self._projects = SqlAlchemyProjectCatalog(session=session)
        self._models = SqlAlchemyModelCatalog(session=session)

        self._definitions = SQLiteDefinitions(session=session)
        self._reviews = SQLiteReviews(session=session)
        self._compilation = SQLiteCompilation(session=session)
        self._publications = SQLitePublications(session=session)
        self._packs = SQLiteSelectedPacks(session=session)

        self._sources = SQLiteSources(session=session)

        self._extraction = SQLiteExtraction(session=session)
        self._discovery_runs = SQLiteDiscoveryRuns(session=session)
        self._reconciliation = SQLiteReconciliation(session=session)

        self._dependencies = PublishedDependencies(
            pins=SQLiteDependencyPins(session=session),
            releases=self._publications,
        )

    @property
    @override
    def audit(self) -> AuditRepository:
        """The audit repository bound to the operation's session."""
        return self._audit

    @property
    @override
    def revisions(self) -> WorkspaceRevisions:
        """The workspace revision repository bound to this session."""
        return self._revisions

    @property
    @override
    def projects(self) -> ProjectCatalog:
        """The project catalog bound to this session."""
        return self._projects

    @property
    @override
    def models(self) -> ModelCatalog:
        """The model catalog bound to this session."""
        return self._models

    @property
    @override
    def definitions(self) -> DefinitionRepository:
        """The authored definition repository bound to this session."""
        return self._definitions

    @property
    @override
    def compilation(self) -> CompilationRepository:
        """The compilation repository bound to this session."""
        return self._compilation

    @property
    @override
    def packs(self) -> SelectedPacks:
        """The reference-pack selection repository bound to this session."""
        return self._packs

    @property
    @override
    def dependencies(self) -> PublishedDependencies:
        """The session-bound resolver for pinned model dependencies."""
        return self._dependencies

    @property
    @override
    def publications(self) -> PublicationRepository:
        """The publication repository bound to this session."""
        return self._publications

    @property
    @override
    def sources(self) -> SourceRepository:
        """The source and evidence repository bound to this session."""
        return self._sources

    @property
    @override
    def extraction(self) -> ExtractionRepository:
        """The extraction repository bound to this session."""
        return self._extraction

    @property
    @override
    def discovery_runs(self) -> DiscoveryRuns:
        """The discovery run repository bound to this session."""
        return self._discovery_runs

    @property
    @override
    def reconciliation(self) -> ReconciliationRepository:
        """The reconciliation repository bound to this session."""
        return self._reconciliation

    @property
    @override
    def reviews(self) -> ReviewRepository:
        """The review case repository bound to this session."""
        return self._reviews

    @property
    @override
    def operations(self) -> IdempotencyRepository:
        """The idempotency repository bound to this session."""
        return self._operations

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        """Open a transaction and commit or roll back before releasing ownership."""
        if self._session.in_transaction():
            raise RuntimeError("The database transaction is already active")

        _ = await self._session.begin()

        try:
            yield
            await DatabaseCompletion.finish(self._session.commit())
        except BaseException:
            await DatabaseCompletion.finish(self._session.rollback())
            raise
