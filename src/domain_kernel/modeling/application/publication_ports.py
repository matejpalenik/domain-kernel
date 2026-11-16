"""Persist immutable preparations and releases within one scoped operation."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.modeling.application.compilation_ports import CompilationTransaction

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.publications import DomainModelBundle, Publication
    from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
    from domain_kernel.shared.contracts import ModelScope, Page
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


class PublicationRepository(Protocol, metaclass=ABCMeta):
    """Store exact preparation and release snapshots without replacement."""

    @abstractmethod
    async def add_preparation(self, *, publication: Publication) -> None:
        """Save a ready or blocked preparation."""

    @abstractmethod
    async def preparation(self, *, scope: ModelScope, publication_id: PublicationId) -> Publication:
        """Load a saved preparation in its exact workspace."""

    @abstractmethod
    async def list_preparations(
        self,
        *,
        scope: ModelScope,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Publication]:
        """Page the stored preparation snapshots for this model."""

    @abstractmethod
    async def add_bundle(self, *, bundle: DomainModelBundle) -> None:
        """Claim the unique version and save its immutable authorization and content."""

    @abstractmethod
    async def bundle(self, *, scope: ModelScope, version: str) -> DomainModelBundle:
        """Read the exact registered version."""

    @abstractmethod
    async def latest(self, *, scope: ModelScope) -> DomainModelBundle | None:
        """Read the last released version by durable publication order."""

    @abstractmethod
    async def list_versions(
        self,
        *,
        scope: ModelScope,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[DomainModelBundle]:
        """Page the archived versions of this exact model."""


@runtime_checkable
class PublicationTransaction(CompilationTransaction, Protocol, metaclass=ABCMeta):
    """Bound repositories used by preparation and publication orchestration."""

    @property
    @abstractmethod
    def publications(self) -> PublicationRepository:
        """Return the bound immutable publication repository."""
