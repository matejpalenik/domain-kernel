"""Durable extraction snapshots kept separate from provider calls."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.shared.application.persistence import Transaction

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
    from domain_kernel.discovery.domain.models import DiscoveryDraft, ExtractionIntent
    from domain_kernel.shared.application.inference import InferenceInput, ModelResponse
    from domain_kernel.shared.contracts import ModelScope


class SchemaStageCall(Protocol, metaclass=ABCMeta):
    """Dispatch a schema stage using the captured request and retry policy."""

    @abstractmethod
    async def __call__(  # noqa: PLR0913 - Match the retained schema stage request.
        self,
        *,
        intent: ExtractionIntent,
        stage: str,
        instructions: str,
        schema: str,
        inputs: tuple[InferenceInput, ...],
        context_json: str,
    ) -> ModelResponse:
        """Return the captured or newly generated stage response."""


@runtime_checkable
class ProfiledDiscoveryGateway(Protocol, metaclass=ABCMeta):
    """Expose versioned execution settings for a restartable discovery workflow."""

    @property
    @abstractmethod
    def discovery_profile(self) -> str | None:
        """Return the stable execution identity where the workflow supplies one."""


@runtime_checkable
class SchemaDiscoveryGateway(Protocol, metaclass=ABCMeta):
    """Advertise support for the SDK's schema-model and schema-review requests."""

    @property
    @abstractmethod
    def supports_schema_discovery(self) -> bool:
        """Return whether the gateway understands versioned schema requests."""


@runtime_checkable
class DiscoveryStageLimits(Protocol, metaclass=ABCMeta):
    """Expose a stricter host budget for retryable discovery stages."""

    @property
    @abstractmethod
    def discovery_stage_attempts(self) -> int:
        """Return the host's maximum number of stage attempts."""


@runtime_checkable
class BindingContractGateway(Protocol, metaclass=ABCMeta):
    """Distinguish a workflow profile from its optional endpoint binding contract."""

    @property
    @abstractmethod
    def binding_contract(self) -> str | None:
        """Return the configured relationship binding contract, when selected."""


@runtime_checkable
class BatchedProposalGateway(Protocol, metaclass=ABCMeta):
    """Opt a staged gateway into bounded proposal persistence."""

    @property
    @abstractmethod
    def batch_proposals(self) -> bool:
        """Return whether the proposal count limit applies to each stored batch."""


class ExtractionRepository(Protocol, metaclass=ABCMeta):
    """Persist fixed extraction intent and a completed typed result."""

    @abstractmethod
    async def reserve(self, *, intent: ExtractionIntent) -> None:
        """Record the exact request's inputs and prompt before calling a model."""

    @abstractmethod
    async def complete(self, *, draft: DiscoveryDraft, batch_size: int | None = None) -> None:
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
