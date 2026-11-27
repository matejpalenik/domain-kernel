from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel.projects.application.protocols.manage_projects import ManageProjects
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.projects.domain.project_info import ProjectInfo
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from domain_kernel.projects.application.commands.create_project import CreateProject
    from domain_kernel.projects.application.protocols.project_catalog import ProjectCatalog
    from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
    from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor


@final
class ManageProjectsService(ManageProjects):
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

    @override
    async def create(self, *, command: CreateProject) -> ProjectInfo:
        """Store a project and its host attribution atomically."""
        TextValidation.require_text(value=command.actor, field="Actor")
        lookup_name, label = LookupNamingPolicy.resolve_names(
            name=command.name, display_name=command.display_name
        )
        project = ProjectInfo(
            id=ProjectId(value=uuid4().hex),
            name=lookup_name,
            display_name=label,
            created_at=datetime.now(tz=UTC),
        )
        resource = AuditResource(
            resource_id=project.id,
            revision=None,
            content_hash=Hashing.hash_json(
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
            actor=command.actor,
            recorded_at=project.created_at,
            before=(),
            after=(resource,),
        )

        async with self._transaction.begin():
            await self._catalog.create(project=project)
            await self._audit.append(record=record)

        return project

    @override
    async def get(self, *, name: str) -> ProjectInfo:
        """Read one exact project name."""
        LookupNamingPolicy.require_lookup_name(name=name)
        async with self._transaction.begin():
            return await self._catalog.get(name=name)

    @override
    async def list(self, *, limit: int, cursor: PageCursor | None) -> Page[ProjectInfo]:
        """Read a page of detached projects."""
        async with self._transaction.begin():
            return await self._catalog.list(limit=limit, cursor=cursor)
