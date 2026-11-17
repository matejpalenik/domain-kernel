"""Immutable inputs, provenance and proposals from an extraction run."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.definitions import Definition, EvidenceBasis
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.shared.contracts import ModelScope, ModelVersion
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)
from domain_kernel.sources.domain.models import Evidence, SourceRevision

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.models import ReferencePackPin


@dataclass(frozen=True, kw_only=True)
class InterpretationContext:
    """The inspected model and its exact approved context for interpretation."""

    scope: ModelScope
    model_description: str
    workspace_revision: int
    approved_definitions: Sequence[Definition] = ()
    reference_pack: ReferencePackPin | None = None
    baseline: ModelVersion | None = None
    dependencies: Sequence[ModelVersion] = ()

    def __post_init__(self) -> None:
        """Snapshot the inspected definition and dependency lists."""
        require_exact(value=self.scope, expected=ModelScope, field="Interpretation scope")
        require_text(value=self.model_description, field="Model description")
        require_exact(value=self.workspace_revision, expected=int, field="Workspace revision")
        if not is_non_string_sequence(self.approved_definitions) or any(
            item.scope != self.scope for item in self.approved_definitions
        ):
            raise TypeError("Use approved definitions from this model")
        object.__setattr__(self, "approved_definitions", tuple(self.approved_definitions))
        object.__setattr__(
            self,
            "dependencies",
            snapshot_sequence(
                items=self.dependencies, item_type=ModelVersion, field="Dependencies"
            ),
        )


@dataclass(frozen=True, kw_only=True)
class DiscoveryPrompt:
    """The SDK's captured instructions and fixed output contract."""

    additional_instructions: str | None
    prompt_override: str | None
    default_prompt_version: str | None
    effective_instructions: str
    response_schema_version: str
    response_schema_hash: ContentHash
    instructions_hash: ContentHash

    def __post_init__(self) -> None:
        """Require nonblank supplied directives and versioned response validation."""
        for value in (
            self.additional_instructions,
            self.prompt_override,
            self.default_prompt_version,
        ):
            if value is not None:
                require_text(value=value, field="Discovery instructions")
        require_text(value=self.effective_instructions, field="Effective instructions")
        require_text(value=self.response_schema_version, field="Response schema version")
        require_exact(value=self.response_schema_hash, expected=ContentHash, field="Schema hash")
        require_exact(value=self.instructions_hash, expected=ContentHash, field="Instructions hash")


@dataclass(frozen=True, kw_only=True)
class ExtractionProvenance:
    """Compiler and provider evidence independent of the original request transport."""

    processing_fingerprint: str
    extractor_id: str
    extractor_version: str
    provider_model_id: str | None = None
    provider_endpoint: str | None = None
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, kw_only=True)
class Proposal:
    """One validated candidate definition awaiting a review decision."""

    id: ProposalId
    scope: ModelScope
    definition: Definition
    basis: EvidenceBasis
    evidence: Sequence[Evidence]
    provenance: ExtractionProvenance
    confidence: Decimal | None = None

    def __post_init__(self) -> None:
        """Keep scoped evidence and bounded, optional confidence."""
        require_exact(value=self.id, expected=ProposalId, field="Proposal identity")
        require_exact(value=self.scope, expected=ModelScope, field="Proposal scope")
        require_exact(value=self.basis, expected=EvidenceBasis, field="Proposal basis")
        require_exact(value=self.provenance, expected=ExtractionProvenance, field="Provenance")
        items = snapshot_sequence(items=self.evidence, item_type=Evidence, field="Evidence")
        if (
            not items
            or self.definition.scope != self.scope
            or self.definition.evidence != items
            or self.definition.basis is not self.basis
        ):
            raise ValueError("Keep the proposal scoped to its definition and cited evidence")
        if self.confidence is not None:
            require_exact(value=self.confidence, expected=Decimal, field="Confidence")
            if not self.confidence.is_finite() or not 0 <= self.confidence <= 1:
                raise ValueError("Use confidence between zero and one")
        object.__setattr__(self, "evidence", items)


@dataclass(frozen=True, kw_only=True)
class ExtractionIntent:
    """Immutable context and prompt recorded before asking the provider."""

    id: DiscoveryDraftId
    run_id: DiscoveryRunId
    context: InterpretationContext
    source_revisions: tuple[SourceRevision, ...]
    prompt: DiscoveryPrompt
    processing_fingerprint: str


@dataclass(frozen=True, kw_only=True)
class DiscoveryDraft:
    """The complete typed extraction result before reconciliation or review."""

    id: DiscoveryDraftId
    scope: ModelScope
    run_id: DiscoveryRunId
    context: InterpretationContext
    source_revisions: Sequence[SourceRevision]
    proposals: Sequence[Proposal]
    prompt: DiscoveryPrompt
    processing_fingerprint: str
    provenance: ExtractionProvenance

    def __post_init__(self) -> None:
        """Bind returned proposals to the exact requested corpus and model scope."""
        require_exact(value=self.id, expected=DiscoveryDraftId, field="Draft identity")
        require_exact(value=self.scope, expected=ModelScope, field="Draft scope")
        require_exact(value=self.run_id, expected=DiscoveryRunId, field="Extraction identity")
        require_exact(value=self.context, expected=InterpretationContext, field="Context")
        require_exact(value=self.prompt, expected=DiscoveryPrompt, field="Prompt")
        require_exact(value=self.provenance, expected=ExtractionProvenance, field="Provenance")
        require_text(value=self.processing_fingerprint, field="Processing fingerprint")
        revisions = snapshot_sequence(
            items=self.source_revisions,
            item_type=SourceRevision,
            field="Source revisions",
        )
        proposals = snapshot_sequence(items=self.proposals, item_type=Proposal, field="Proposals")
        if (
            self.context.scope != self.scope
            or not revisions
            or any(
                proposal.scope != self.scope
                or any(citation.source not in revisions for citation in proposal.evidence)
                for proposal in proposals
            )
        ):
            raise ValueError("Keep the draft bound to its original model and corpus")
        object.__setattr__(self, "source_revisions", revisions)
        object.__setattr__(self, "proposals", proposals)


@unique
class RunStatus(StrEnum):
    """Business stages of a discovery run."""

    INGESTING = "ingesting"
    EXTRACTING = "extracting"
    RECONCILING = "reconciling"
    NEEDS_REVIEW = "needs_review"
    READY_TO_PREPARE = "ready_to_prepare"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, kw_only=True)
class DiscoveryProgress:
    """A bounded progress notification for the caller."""

    scope: ModelScope
    run_id: DiscoveryRunId
    stage: RunStatus
    completed: int
    total: int | None


type ProgressCallback = Callable[[DiscoveryProgress], None]
