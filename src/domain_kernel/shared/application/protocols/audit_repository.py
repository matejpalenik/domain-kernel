from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.model_id import ModelId
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.application.results.page import Page
    from domain_kernel.shared.application.results.page_cursor import PageCursor
    from domain_kernel.shared.domain.entities.audit_record import AuditRecord


class AuditRepository(Protocol, metaclass=ABCMeta):
    """Append and inspect detached, attributed events."""

    @abstractmethod
    async def append(self, *, record: AuditRecord) -> None:
        """Include an immutable event in the operation's transaction."""

    @abstractmethod
    async def list(
        self,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[AuditRecord]:
        """List a stable snapshot of the project or model history."""
