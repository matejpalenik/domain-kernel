"""Immutable inputs, provenance and proposals from an extraction run."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.definitions import (
    Definition,
    EvidenceBasis,
    RelationshipDefinition,
)
from domain_kernel.discovery.domain.bindings import HeldRelationship, RelationshipBinding
from domain_kernel.discovery.domain.coverage import DiscoveryCoverage
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.schema_evidence import (
    SchemaMappingHint,
    SchemaObservation,
    SchemaReviewEvidence,
)
from domain_kernel.discovery.domain.schema_options import SchemaDiscoveryOptions
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.questions import Question
from domain_kernel.shared.contracts import Issue, ModelScope, ModelVersion
from domain_kernel.shared.hashing import hash_bytes
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
    from domain_kernel.shared.enums.issue_severity import IssueSeverity


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
    schema_options: SchemaDiscoveryOptions | None = None

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
        if self.schema_options is not None:
            require_exact(
                value=self.schema_options, expected=SchemaDiscoveryOptions, field="Schema options"
            )


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
    schema_review: SchemaReviewEvidence | None = None

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
    relationship_bindings: Sequence[RelationshipBinding] = ()
    held_relationships: Sequence[HeldRelationship] = ()
    coverage: tuple[DiscoveryCoverage, ...] = ()
    schema_questions: tuple[Question, ...] = ()
    schema_modeled: bool = False
    schema_observations: tuple[SchemaObservation, ...] = ()
    schema_mappings: tuple[SchemaMappingHint, ...] = ()
    schema_review_receipt: str | None = None

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
        require_exact(value=self.schema_modeled, expected=bool, field="Schema modeling")
        questions = snapshot_sequence(
            items=self.schema_questions, item_type=Question, field="Schema questions"
        )
        if any(citation.source not in revisions for q in questions for citation in q.evidence):
            raise ValueError("Keep schema questions bound to the captured source revisions.")
        object.__setattr__(self, "schema_questions", questions)
        self._check_schema_evidence(revisions=revisions, proposals=proposals)
        bindings = snapshot_sequence(
            items=self.relationship_bindings,
            item_type=RelationshipBinding,
            field="Relationship bindings",
        )
        if len({binding.claim_id for binding in bindings}) != len(bindings):
            raise ValueError("Record each relationship claim once.")
        self._check_relationship_bindings(bindings=bindings, proposals=proposals)
        object.__setattr__(self, "relationship_bindings", bindings)
        held = snapshot_sequence(
            items=self.held_relationships, item_type=HeldRelationship, field="Held relationships"
        )
        if len({claim.claim_id for claim in held}) != len(held) or any(
            witness.evidence.source not in revisions for claim in held for witness in claim.evidence
        ):
            raise ValueError(
                "Keep one held relationship per claim within the captured source revisions."
            )
        object.__setattr__(self, "held_relationships", held)
        coverage = snapshot_sequence(
            items=self.coverage, item_type=DiscoveryCoverage, field="Discovery coverage"
        )
        if len({item.source for item in coverage}) != len(coverage) or any(
            item.source not in revisions for item in coverage
        ):
            raise ValueError("Keep one discovery coverage manifest per captured source.")
        object.__setattr__(self, "coverage", coverage)

    def _check_schema_evidence(
        self, *, revisions: Sequence[SourceRevision], proposals: Sequence[Proposal]
    ) -> None:
        observations = snapshot_sequence(
            items=self.schema_observations, item_type=SchemaObservation, field="Schema observations"
        )
        mappings = snapshot_sequence(
            items=self.schema_mappings, item_type=SchemaMappingHint, field="Schema mappings"
        )
        local = {proposal.definition.id for proposal in proposals}
        if (
            len({item.id for item in observations}) != len(observations)
            or any(
                not item.witnesses
                or any(w.evidence.source not in revisions for w in item.witnesses)
                for item in observations
            )
            or any(item.definition not in local for item in mappings)
            or (mappings and self.context.reference_pack is None)
            or len({(item.definition, item.reference) for item in mappings}) != len(mappings)
        ):
            raise ValueError("Keep schema evidence and mappings within the captured draft.")
        if self.schema_review_receipt is not None:
            require_text(value=self.schema_review_receipt, field="Schema review receipt")
        object.__setattr__(self, "schema_observations", observations)
        object.__setattr__(self, "schema_mappings", mappings)

    def _check_relationship_bindings(
        self, *, bindings: Sequence[RelationshipBinding], proposals: Sequence[Proposal]
    ) -> None:
        if not bindings:
            return
        bodies = {
            item.definition.id: item.definition.body
            for item in proposals
            if isinstance(item.definition.body, RelationshipDefinition)
        }
        for binding in bindings:
            witnesses = (w.evidence for w in (*binding.evidence, *binding.identity_evidence))
            endpoints = (
                e.evidence
                for e in (
                    binding.source,
                    binding.target,
                    binding.previous_source,
                    binding.previous_target,
                )
                if e is not None
            )
            if any(e.source not in self.source_revisions for e in (*witnesses, *endpoints)):
                raise ValueError("Keep relationship evidence within the captured source revisions.")
            if binding.relationship_id is not None:
                body = bodies.pop(binding.relationship_id, None)
                if (
                    body is None
                    or binding.source is None
                    or binding.target is None
                    or body.source_concept_id != binding.source.definition_id
                    or body.target_concept_id != binding.target.definition_id
                ):
                    raise ValueError(
                        "Keep the issued relationship and ordered concept IDs together."
                    )
        if bodies:
            raise ValueError("Bind every emitted staged relationship.")


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


@dataclass(frozen=True, kw_only=True)
class DiscoveryFailure:
    """A sanitized failure at an exact source revision or run stage."""

    source_label: str
    source: SourceRevision | None
    issue: Issue
    retryable: bool

    def __post_init__(self) -> None:
        """Keep the single structured diagnostic and its scope."""
        require_text(value=self.source_label, field="Discovery source label")
        if self.source is not None:
            require_exact(value=self.source, expected=SourceRevision, field="Discovery source")
        require_exact(value=self.issue, expected=Issue, field="Discovery issue")
        require_exact(value=self.retryable, expected=bool, field="Retryability")

    @property
    def message(self) -> str:
        """Return the underlying sanitized issue message."""
        return self.issue.message

    @property
    def code(self) -> str:
        """Return the underlying stable issue code."""
        return self.issue.code

    @property
    def severity(self) -> IssueSeverity:
        """Return the underlying issue severity."""
        return self.issue.severity


@dataclass(frozen=True, kw_only=True)
class DiscoveryResult:
    """A detached checkpoint of the discovered work and review queue."""

    id: DiscoveryRunId
    scope: ModelScope
    version: int
    status: RunStatus
    failures: Sequence[DiscoveryFailure]
    discovery_id: DiscoveryDraftId | None
    reconciliation_id: AlignmentId | None
    context: InterpretationContext
    prompt: DiscoveryPrompt
    parent_run_id: DiscoveryRunId | None = None

    def __post_init__(self) -> None:
        """Bind output and failures to the captured run context."""
        require_exact(value=self.id, expected=DiscoveryRunId, field="Run ID")
        require_exact(value=self.scope, expected=ModelScope, field="Run scope")
        require_exact(value=self.version, expected=int, field="Run version")
        require_exact(value=self.status, expected=RunStatus, field="Run status")
        require_exact(value=self.context, expected=InterpretationContext, field="Context")
        require_exact(value=self.prompt, expected=DiscoveryPrompt, field="Prompt")
        if self.parent_run_id is not None:
            require_exact(
                value=self.parent_run_id, expected=DiscoveryRunId, field="Parent discovery run"
            )
            if self.parent_run_id == self.id:
                raise ValueError("Link continuation to an earlier run.")
        if self.version < 1 or self.context.scope != self.scope:
            raise ValueError("Use a positive run version and the exact model scope.")
        if self.discovery_id is not None:
            require_exact(value=self.discovery_id, expected=DiscoveryDraftId, field="Draft ID")
        if self.reconciliation_id is not None:
            require_exact(value=self.reconciliation_id, expected=AlignmentId, field="Alignment ID")
            if self.discovery_id is None:
                raise ValueError("Bind reconciliation to its extracted draft.")
        errors = snapshot_sequence(
            items=self.failures, item_type=DiscoveryFailure, field="Failures"
        )
        if any(
            item.source is not None and item.source.project_id != self.scope.project_id
            for item in errors
        ):
            raise ValueError("Use source failures scoped to this discovery project.")
        object.__setattr__(self, "failures", errors)


@dataclass(frozen=True, kw_only=True)
class SourceCheckpoint:
    """Progress on one immutable input, retained independently of the worker."""

    source: SourceRevision
    draft_id: DiscoveryDraftId | None = None
    alignment_id: AlignmentId | None = None
    failure: DiscoveryFailure | None = None

    def __post_init__(self) -> None:
        """Keep each checkpoint attached to its exact source and ordered effects."""
        require_exact(value=self.source, expected=SourceRevision, field="Checkpoint source")
        if self.draft_id is not None:
            require_exact(value=self.draft_id, expected=DiscoveryDraftId, field="Draft ID")
        if self.alignment_id is not None:
            require_exact(value=self.alignment_id, expected=AlignmentId, field="Alignment ID")
            if self.draft_id is None or self.failure is not None:
                raise ValueError("Finish the exact draft before completing its alignment.")
        if self.failure is not None:
            require_exact(value=self.failure, expected=DiscoveryFailure, field="Checkpoint failure")
            if self.failure.source != self.source:
                raise ValueError("Record failure against this exact source revision.")


@dataclass(frozen=True, kw_only=True)
class DiscoveryRun:
    """The replayable request and all of its durable source checkpoints."""

    snapshot: DiscoveryResult
    actor: str
    schema_json: str
    tasks: tuple[SourceCheckpoint, ...]
    workflow_profile: str | None = None
    schema_version: str | None = None

    def __post_init__(self) -> None:
        """Require the captured schema bytes and detached exact source checkpoints."""
        require_text(value=self.actor, field="Run actor")
        require_text(value=self.schema_json, field="Response schema")
        if self.workflow_profile is not None:
            require_text(value=self.workflow_profile, field="Discovery workflow profile")
        if self.schema_version is not None:
            require_text(value=self.schema_version, field="Discovery schema policy")
        if self.snapshot.prompt.response_schema_hash != hash_bytes(
            content=self.schema_json.encode()
        ):
            raise ValueError("Use the exact response schema captured before discovery.")
        tasks = snapshot_sequence(
            items=self.tasks, item_type=SourceCheckpoint, field="Source checkpoints"
        )
        if (
            not tasks
            or len({item.source for item in tasks}) != len(tasks)
            or any(item.source.project_id != self.snapshot.scope.project_id for item in tasks)
        ):
            raise ValueError("Use distinct source checkpoints scoped to this project.")
        object.__setattr__(self, "tasks", tasks)

    def advance(
        self,
        *,
        status: RunStatus,
        task: SourceCheckpoint | None = None,
    ) -> DiscoveryRun:
        """Record a stage or advance exactly one source while preserving earlier work."""
        tasks = self.tasks
        snapshot = self.snapshot
        draft_id = snapshot.discovery_id
        alignment_id = snapshot.reconciliation_id
        if task is not None:
            if all(item.source != task.source for item in tasks):
                raise ValueError("Advance a source captured by this discovery run.")
            tasks = tuple(task if item.source == task.source else item for item in tasks)
            if task.draft_id is not None and self.schema_version is None:
                draft_id, alignment_id = task.draft_id, task.alignment_id
        return replace(
            self,
            tasks=tasks,
            snapshot=replace(
                snapshot,
                version=snapshot.version + 1,
                status=status,
                failures=tuple(item.failure for item in tasks if item.failure is not None),
                discovery_id=draft_id,
                reconciliation_id=alignment_id,
            ),
        )
