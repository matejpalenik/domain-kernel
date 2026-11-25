"""The persistence capabilities required by manual review."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.shared.application.persistence import Transaction

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
    from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
    from domain_kernel.review.domain.enums.case_kind import CaseKind
    from domain_kernel.review.domain.enums.case_status import CaseStatus
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
    from domain_kernel.review.domain.models import DecisionRecord, ReviewCase, ReviewReceipt
    from domain_kernel.shared.contracts import ModelScope, Page
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


class DefinitionRepository(Protocol, metaclass=ABCMeta):
    """Own reserved definition names and immutable revisions."""

    @abstractmethod
    async def reserve(self, *, definition: Definition) -> None:
        """Reserve one ID and unique model-local name on proposal."""

    @abstractmethod
    async def release(self, *, definition: Definition) -> None:
        """Release the name of a rejected, never-approved identity."""

    @abstractmethod
    async def append(self, *, definition: Definition) -> None:
        """Append an immutable revision under its expected current guard."""

    @abstractmethod
    async def get(
        self,
        *,
        scope: ModelScope,
        name: str | None,
        definition_id: DefinitionId | None,
        revision: int | None,
    ) -> Definition:
        """Read one materialized definition by its exact name or ID."""

    @abstractmethod
    async def list(
        self,
        *,
        scope: ModelScope,
        status: DefinitionStatus | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Definition]:
        """Read current revisions in one model."""

    @abstractmethod
    async def active(self, *, scope: ModelScope) -> tuple[Definition, ...]:
        """Capture current active definitions for the prospective graph check."""

    @abstractmethod
    async def history(
        self,
        *,
        scope: ModelScope,
        definition_id: DefinitionId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[Definition]:
        """Read immutable revisions of one exact identity."""


class ReviewRepository(Protocol, metaclass=ABCMeta):
    """Read and append cases and attributed decisions."""

    @abstractmethod
    async def add(self, *, case: ReviewCase) -> None:
        """Add a new review case and its initial version."""

    @abstractmethod
    async def save(self, *, case: ReviewCase, expected_version: int) -> None:
        """Advance the case guard and preserve its previous version."""

    @abstractmethod
    async def get(
        self,
        *,
        scope: ModelScope,
        case_id: ReviewCaseId,
        version: int | None,
    ) -> ReviewCase:
        """Read a current or exact historical case snapshot."""

    @abstractmethod
    async def list(  # noqa: PLR0913 - Preserve the complete review filter set.
        self,
        *,
        scope: ModelScope,
        kind: CaseKind | None,
        status: CaseStatus | None,
        limit: int,
        cursor: PageCursor | None,
        run_id: DiscoveryRunId | None = None,
        reconciliation_id: AlignmentId | None = None,
    ) -> Page[ReviewCase]:
        """Read current cases filtered within one workspace."""

    @abstractmethod
    async def record(self, *, decision: DecisionRecord, receipt: ReviewReceipt) -> None:
        """Append an attributed decision and exact replay result."""

    @abstractmethod
    async def receipt(self, *, scope: ModelScope, decision_id: DecisionId) -> ReviewReceipt:
        """Restore the original committed receipt."""

    @abstractmethod
    async def history(
        self,
        *,
        scope: ModelScope,
        case_id: ReviewCaseId,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[DecisionRecord]:
        """Page through immutable decisions for this case."""


@runtime_checkable
class ReviewTransaction(Transaction, Protocol, metaclass=ABCMeta):
    """Operation-local capabilities for use at the composition boundary."""

    @property
    @abstractmethod
    def definitions(self) -> DefinitionRepository:
        """Return the bound definition repository."""

    @property
    @abstractmethod
    def reviews(self) -> ReviewRepository:
        """Return the bound review repository."""
