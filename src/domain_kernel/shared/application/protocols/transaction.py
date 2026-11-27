from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol

from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager

if TYPE_CHECKING:
    from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
    from domain_kernel.shared.application.protocols.idempotency_repository import (
        IdempotencyRepository,
    )
    from domain_kernel.shared.application.protocols.workspace_revisions import WorkspaceRevisions


class Transaction(TransactionManager, Protocol, metaclass=ABCMeta):
    """Bound repository bundle used by operation composition."""

    @property
    @abstractmethod
    def operations(self) -> IdempotencyRepository:
        """The idempotency repository sharing this operation's transaction."""

    @property
    @abstractmethod
    def audit(self) -> AuditRepository:
        """The audit repository sharing this operation's transaction."""

    @property
    @abstractmethod
    def revisions(self) -> WorkspaceRevisions:
        """The workspace revision guard sharing this operation's transaction."""
