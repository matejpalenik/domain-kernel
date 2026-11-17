"""Scoped catalog ports and use cases for workspace setup."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, final
from uuid import uuid4

from domain_kernel._shared.application.persistence import Transaction
from domain_kernel._shared.domain.audit import AuditAction, AuditOutcome, AuditRecord, AuditResource
from domain_kernel._shared.domain.naming import require_lookup_name, resolve_names
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.models import ModelInfo
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.projects.domain.project_info import ProjectInfo
from domain_kernel.reference_packs.api.packs import ReferencePack
from domain_kernel.reference_packs.domain.contracts import COVERAGE_VALIDATOR, ObligationKind
from domain_kernel.shared.contracts import ModelScope
from domain_kernel.shared.errors import InvalidReferencePackError, MissingCapabilityError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validation import require_exact, require_text

if TYPE_CHECKING:
    from domain_kernel._shared.application.persistence import AuditRepository, TransactionManager
    from domain_kernel.reference_packs.application.selection_ports import SelectedPacks
    from domain_kernel.shared.contracts import Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


class ProjectCatalog(Protocol, metaclass=ABCMeta):
    """Persist and look up named projects."""

    @abstractmethod
    async def create(self, *, project: ProjectInfo) -> None:
        """Add one globally unique project name."""

    @abstractmethod
    async def get(self, *, name: str) -> ProjectInfo:
        """Find a project by its exact name."""

    @abstractmethod
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        """Page through projects by stable name."""


class ModelCatalog(Protocol, metaclass=ABCMeta):
    """Persist and look up models inside one project."""

    @abstractmethod
    async def create(self, *, info: ModelInfo) -> None:
        """Add one model by its project-local name."""

    @abstractmethod
    async def get(self, *, project_id: ProjectId, name: str) -> ModelInfo:
        """Find a model by its exact scoped name."""

    @abstractmethod
    async def list(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[ModelInfo]:
        """Page through one project's models by name."""


class CatalogTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Operation-local resources used by project and model composition."""

    @property
    @abstractmethod
    def projects(self) -> ProjectCatalog:
        """Return the bound project repository."""

    @property
    @abstractmethod
    def models(self) -> ModelCatalog:
        """Return the bound model repository."""


@final
class Projects:
    """Use cases for global project creation and lookup."""

    def __init__(
        self,
        *,
        catalog: ProjectCatalog,
        audit: AuditRepository,
        transaction: TransactionManager,
    ) -> None:
        """Bind project capabilities for one operation."""
        self._catalog = catalog
        self._audit = audit
        self._transaction = transaction

    async def create(
        self,
        *,
        actor: str,
        display_name: str | None,
        name: str | None,
    ) -> ProjectInfo:
        """Store a project and its host attribution atomically."""
        require_text(value=actor, field="Actor")
        lookup_name, label = resolve_names(name=name, display_name=display_name)
        project = ProjectInfo(
            id=ProjectId(value=uuid4().hex),
            name=lookup_name,
            display_name=label,
            created_at=datetime.now(tz=UTC),
        )
        resource = AuditResource(
            resource_id=project.id,
            revision=None,
            content_hash=hash_json(
                value={
                    "id": project.id.value,
                    "name": project.name,
                    "display_name": project.display_name,
                    "created_at": project.created_at.isoformat(),
                }
            ),
        )
        record = AuditRecord(
            id=AuditId(value=uuid4().hex),
            project_id=project.id,
            model_id=None,
            action=AuditAction.CREATE_PROJECT,
            outcome=AuditOutcome.SUCCEEDED,
            actor=actor,
            recorded_at=project.created_at,
            before=(),
            after=(resource,),
        )
        async with self._transaction.begin():
            await self._catalog.create(project=project)
            await self._audit.append(record=record)
        return project

    async def get(self, *, name: str) -> ProjectInfo:
        """Read one exact project name."""
        require_lookup_name(name=name)
        async with self._transaction.begin():
            return await self._catalog.get(name=name)

    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        """Read a page of detached projects."""
        async with self._transaction.begin():
            return await self._catalog.list(limit=limit, cursor=cursor)


@final
class Models:
    """Use cases for creating and reopening independent model workspaces."""

    def __init__(
        self,
        *,
        project_id: ProjectId,
        catalog: ModelCatalog,
        audit: AuditRepository,
        transaction: TransactionManager,
        packs: SelectedPacks | None = None,
    ) -> None:
        """Bind a project and the capabilities for its operation."""
        self._project_id = project_id
        self._catalog = catalog
        self._audit = audit
        self._transaction = transaction
        self._packs = packs

    async def create(  # noqa: PLR0913 - Explicit workspace creation and optional pack selection.
        self,
        *,
        actor: str,
        kind: ModelKind,
        description: str,
        display_name: str | None,
        name: str | None,
        reference_pack: ReferencePack | None = None,
    ) -> ModelInfo:
        """Store model intent, stable names and a creation audit event together."""
        require_text(value=actor, field="Actor")
        require_text(value=description, field="Model description")
        require_exact(value=kind, expected=ModelKind, field="Model kind")
        if reference_pack is not None:
            _validate_selection(pack=reference_pack)
            if self._packs is None:
                raise MissingCapabilityError(message="Configure durable selected-pack persistence")
        lookup_name, label = resolve_names(name=name, display_name=display_name)
        scope = ModelScope(project_id=self._project_id, model_id=ModelId(value=uuid4().hex))
        info = ModelInfo(
            scope=scope,
            name=lookup_name,
            display_name=label,
            kind=kind,
            description=description,
            revision=0,
            reference_pack=None if reference_pack is None else reference_pack.pin,
            created_at=datetime.now(tz=UTC),
        )
        resource = AuditResource(
            resource_id=scope.model_id,
            revision=info.revision,
            content_hash=hash_json(
                value={
                    "project_id": scope.project_id.value,
                    "model_id": scope.model_id.value,
                    "name": info.name,
                    "display_name": info.display_name,
                    "kind": info.kind.value,
                    "description": info.description,
                    "revision": info.revision,
                    "reference_pack": None
                    if reference_pack is None
                    else {
                        "key": reference_pack.pin.key,
                        "version": reference_pack.pin.version,
                        "content_hash": reference_pack.pin.content_hash.value,
                    },
                    "baseline": None,
                    "dependencies": [],
                    "created_at": info.created_at.isoformat(),
                }
            ),
        )
        record = AuditRecord(
            id=AuditId(value=uuid4().hex),
            project_id=scope.project_id,
            model_id=scope.model_id,
            action=AuditAction.CREATE_MODEL,
            outcome=AuditOutcome.SUCCEEDED,
            actor=actor,
            recorded_at=info.created_at,
            before=(),
            after=(resource,),
        )
        async with self._transaction.begin():
            await self._catalog.create(info=info)
            if reference_pack is not None and self._packs is not None:
                await self._packs.attach(scope=info.scope, pack=reference_pack)
            await self._audit.append(record=record)
        return info

    async def get(self, *, name: str) -> ModelInfo:
        """Read a named model from the bound project."""
        require_lookup_name(name=name)
        async with self._transaction.begin():
            return await self._catalog.get(project_id=self._project_id, name=name)

    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ModelInfo]:
        """Read detached model metadata from the bound project."""
        async with self._transaction.begin():
            return await self._catalog.list(project_id=self._project_id, limit=limit, cursor=cursor)


def _validate_selection(*, pack: ReferencePack) -> None:
    require_exact(value=pack, expected=ReferencePack, field="Selected reference pack")
    validation = pack.validate()
    if not validation.valid:
        raise InvalidReferencePackError(issues=validation.issues)
    if any(
        item.required
        and (item.kind is not ObligationKind.COVERAGE or item.validator_id != COVERAGE_VALIDATOR)
        for item in pack.obligations
    ):
        raise MissingCapabilityError(message="Configure the required reference-pack validators")
