"""Typed reconciliation capabilities independent of storage and optional adapters."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.discovery.application.ports import ExtractionTransaction
from domain_kernel.reference_packs.application.selection_ports import PackSelectionTransaction
from domain_kernel.review.application.ports import ReviewTransaction
from domain_kernel.shared.application.protocols.catalog_transaction import CatalogTransaction

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
    from domain_kernel.reconciliation.domain.models import Alignment
    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


@runtime_checkable
class SimilarityScorer(Protocol, metaclass=ABCMeta):
    """A host-selected lexical scorer with values between zero and one."""

    @abstractmethod
    def score(self, *, left: str, right: str) -> float:
        """Compare labels for candidate selection."""
        ...


class ReconciliationRepository(Protocol, metaclass=ABCMeta):
    """Persist one prepared checkpoint for a completed discovery draft."""

    @abstractmethod
    async def get(self, *, scope: ModelScope, alignment_id: AlignmentId) -> Alignment:
        """Find an exact scoped checkpoint."""
        ...

    @abstractmethod
    async def for_draft(
        self, *, scope: ModelScope, discovery_id: DiscoveryDraftId
    ) -> Alignment | None:
        """Find a prior preparation of the same immutable draft."""
        ...

    @abstractmethod
    async def add(self, *, alignment: Alignment) -> None:
        """Store the prepared checkpoint in the cases' transaction."""
        ...


@runtime_checkable
class ReconciliationTransaction(
    CatalogTransaction, ReviewTransaction, ExtractionTransaction, PackSelectionTransaction, Protocol
):
    """Capabilities for atomic preparation in the current model context."""

    @property
    @abstractmethod
    def reconciliation(self) -> ReconciliationRepository:
        """Access scoped reconciliation checkpoints."""
        ...
