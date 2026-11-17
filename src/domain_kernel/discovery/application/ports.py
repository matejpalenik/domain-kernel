"""Durable extraction snapshots kept separate from provider calls."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel._shared.application.persistence import Transaction

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.discovery.domain.models import DiscoveryDraft, ExtractionIntent
    from domain_kernel.shared.contracts import ModelScope


class ExtractionRepository(Protocol, metaclass=ABCMeta):
    """Persist fixed extraction intent and a completed typed result."""

    @abstractmethod
    async def reserve(self, *, intent: ExtractionIntent) -> None:
        """Record the exact request's inputs and prompt before calling a model."""

    @abstractmethod
    async def complete(self, *, draft: DiscoveryDraft) -> None:
        """Store exactly one validated result for the reserved draft."""

    @abstractmethod
    async def draft(self, *, identifier: DiscoveryDraftId, scope: ModelScope) -> DiscoveryDraft:
        """Reload the exact completed draft in its owning workspace."""


@runtime_checkable
class ExtractionTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Join extraction snapshots with the operation lease and replay outcome."""

    @property
    @abstractmethod
    def extraction(self) -> ExtractionRepository:
        """Access the current session's extraction snapshots."""
