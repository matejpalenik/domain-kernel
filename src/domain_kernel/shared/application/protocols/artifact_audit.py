from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain_kernel.shared.domain.entities.audit_record import AuditRecord
    from domain_kernel.shared.identifiers.audit_id import AuditId


@runtime_checkable
class ArtifactAudit(Protocol, metaclass=ABCMeta):
    """Read exact audit snapshots used by resumable delivery."""

    @abstractmethod
    async def get(self, *, audit_id: AuditId) -> AuditRecord | None:
        """Return the exact saved event by its durable identity, or None if it is absent."""
