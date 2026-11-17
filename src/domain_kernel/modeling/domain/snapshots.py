"""Immutable compilation, validation and readiness records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from importlib import import_module
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from domain_kernel._shared.domain.acceptance import AcceptanceCheckResult
from domain_kernel._shared.domain.changes import ChangeSet, ReferenceDisposition, SourceAlignment
from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    Process,
    require_definition_selector,
    typed_definition,
)
from domain_kernel._shared.domain.dependency_requests import DependencyChangeRequest
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.errors.definition_errors import (
    DefinitionKindMismatchError,
    DefinitionNotFoundError,
)
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reference_packs.api.packs import ReferencePack
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.shared.contracts import CandidatePin, Issue, ModelScope, ModelVersion
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.authoring import ModelChangePlan
    from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.review.domain.decisions import ReviewAction
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId
    from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
    from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId


@dataclass(frozen=True, kw_only=True)
class VisibleQuestion:
    """An attributed question explicitly reviewed as optional."""

    id: QuestionId
    text: str
    scope_text: str
    rationale: str
    reviewer: str
    decision_id: DecisionId


@dataclass(frozen=True, kw_only=True)
class ReviewSnapshot:
    """Capture resolved decisions and remaining required review gaps."""

    scope: ModelScope
    version: int
    content_hash: ContentHash
    decisions: Sequence[DecisionRecord]
    pending_required: int
    questions: Sequence[VisibleQuestion] = ()

    def __post_init__(self) -> None:
        """Freeze review inputs independently of later workspace changes."""
        require_exact(value=self.scope, expected=ModelScope, field="Review scope")
        require_exact(value=self.version, expected=int, field="Review version")
        require_exact(value=self.content_hash, expected=ContentHash, field="Review hash")
        require_exact(value=self.pending_required, expected=int, field="Required review gaps")
        if self.version < 0 or self.pending_required < 0:
            raise ValueError("Review versions and pending counts are nonnegative")
        object.__setattr__(
            self,
            "decisions",
            snapshot_sequence(items=self.decisions, item_type=DecisionRecord, field="Decisions"),
        )
        object.__setattr__(
            self,
            "questions",
            snapshot_sequence(items=self.questions, item_type=VisibleQuestion, field="Questions"),
        )


@dataclass(frozen=True, kw_only=True)
class ModelContent:
    """Materialized current definitions, tombstones and dispositions."""

    definitions: Sequence[Definition]
    retired_definitions: Sequence[Definition] = ()
    source_alignments: Sequence[SourceAlignment] = ()
    reference_dispositions: Sequence[ReferenceDisposition] = ()

    def __post_init__(self) -> None:
        """Detach each part of the candidate graph."""
        object.__setattr__(
            self,
            "definitions",
            snapshot_sequence(items=self.definitions, item_type=Definition, field="Definitions"),
        )
        object.__setattr__(
            self,
            "retired_definitions",
            snapshot_sequence(
                items=self.retired_definitions, item_type=Definition, field="Retired definitions"
            ),
        )
        object.__setattr__(
            self,
            "source_alignments",
            snapshot_sequence(
                items=self.source_alignments, item_type=SourceAlignment, field="Source alignments"
            ),
        )
        object.__setattr__(
            self,
            "reference_dispositions",
            snapshot_sequence(
                items=self.reference_dispositions,
                item_type=ReferenceDisposition,
                field="Reference dispositions",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """An inspected, immutable model graph with exact review and dependency pins."""

    id: CandidateId
    scope: ModelScope
    kind: ModelKind
    description: str
    workspace_revision: int
    review_snapshot_version: int
    review_snapshot_hash: ContentHash
    content_hash: ContentHash
    content: ModelContent
    reference_pack: ReferencePackPin | None = None
    baseline: ModelVersion | None = None
    dependencies: Sequence[ModelVersion] = ()
    dependency_bundles: Sequence[DomainModelBundle] = field(
        default=(),
        metadata={"wire_omit_empty": True},
    )
    decisions: Sequence[DecisionRecord] = ()
    nonblocking_questions: Sequence[VisibleQuestion] = ()

    def __post_init__(self) -> None:
        """Require exact identities and freeze captured versions and decisions."""
        require_exact(value=self.id, expected=CandidateId, field="Candidate ID")
        require_exact(value=self.scope, expected=ModelScope, field="Candidate scope")
        require_exact(value=self.kind, expected=ModelKind, field="Candidate kind")
        require_text(value=self.description, field="Model description")
        require_exact(value=self.workspace_revision, expected=int, field="Workspace revision")
        require_exact(value=self.review_snapshot_version, expected=int, field="Review version")
        require_exact(value=self.review_snapshot_hash, expected=ContentHash, field="Review hash")
        require_exact(value=self.content_hash, expected=ContentHash, field="Candidate hash")
        require_exact(value=self.content, expected=ModelContent, field="Model content")
        if self.baseline is not None:
            require_exact(value=self.baseline, expected=ModelVersion, field="Direct baseline")
        if self.workspace_revision < 0 or self.review_snapshot_version < 0:
            raise ValueError("Snapshot versions are nonnegative")
        object.__setattr__(
            self,
            "dependencies",
            snapshot_sequence(
                items=self.dependencies, item_type=ModelVersion, field="Dependencies"
            ),
        )
        bundles = snapshot_sequence(
            items=self.dependency_bundles,
            item_type=DomainModelBundle,
            field="Dependency bundles",
        )
        if tuple(bundle.model_version for bundle in bundles) != self.dependencies:
            raise ValueError("Supply one exact published bundle for every direct dependency pin")
        object.__setattr__(self, "dependency_bundles", bundles)
        object.__setattr__(
            self,
            "decisions",
            snapshot_sequence(items=self.decisions, item_type=DecisionRecord, field="Decisions"),
        )
        object.__setattr__(
            self,
            "nonblocking_questions",
            snapshot_sequence(
                items=self.nonblocking_questions,
                item_type=VisibleQuestion,
                field="Optional questions",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ValidationReport:
    """Validation findings captured for one exact candidate."""

    id: ValidationReportId
    scope: ModelScope
    candidate_id: CandidateId
    candidate_hash: ContentHash
    validator_fingerprint: str
    reference_pack: ReferencePackPin | None
    issues: Sequence[Issue]
    acceptance: Sequence[AcceptanceCheckResult] = ()

    def __post_init__(self) -> None:
        """Detach findings and acceptance results from evaluator inputs."""
        require_exact(value=self.id, expected=ValidationReportId, field="Validation report ID")
        require_exact(value=self.scope, expected=ModelScope, field="Validation scope")
        require_exact(value=self.candidate_id, expected=CandidateId, field="Validated candidate ID")
        require_exact(
            value=self.candidate_hash, expected=ContentHash, field="Validated candidate hash"
        )
        require_text(value=self.validator_fingerprint, field="Validator fingerprint")

        object.__setattr__(
            self,
            "issues",
            snapshot_sequence(items=self.issues, item_type=Issue, field="Validation issues"),
        )
        object.__setattr__(
            self,
            "acceptance",
            snapshot_sequence(
                items=self.acceptance,
                item_type=AcceptanceCheckResult,
                field="Acceptance results",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ReadinessCheck:
    """One explicit diagnostic in a release eligibility evaluation."""

    code: str
    passed: bool
    required: bool
    resource_labels: Sequence[str]
    message: str

    def __post_init__(self) -> None:
        """Freeze exact diagnostic labels."""
        object.__setattr__(
            self,
            "resource_labels",
            snapshot_sequence(
                items=self.resource_labels,
                item_type=str,
                field="Resource labels",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class Readiness:
    """Release readiness explained by independently captured requirements."""

    scope: ModelScope
    candidate_id: CandidateId
    candidate_hash: ContentHash
    ready: bool
    checks: Sequence[ReadinessCheck]
    blockers: Sequence[Issue]
    nonblocking_questions: Sequence[VisibleQuestion]

    def __post_init__(self) -> None:
        """Hold immutable diagnostics and reviewed optional questions."""
        object.__setattr__(
            self,
            "checks",
            snapshot_sequence(items=self.checks, item_type=ReadinessCheck, field="Checks"),
        )
        object.__setattr__(
            self,
            "blockers",
            snapshot_sequence(items=self.blockers, item_type=Issue, field="Blockers"),
        )
        object.__setattr__(
            self,
            "nonblocking_questions",
            snapshot_sequence(
                items=self.nonblocking_questions,
                item_type=VisibleQuestion,
                field="Optional questions",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class PublicationRules:
    """Captured publication policy for reviewed optional questions."""

    allow_reviewed_nonblocking_questions: bool = True

    def __post_init__(self) -> None:
        """Require a strict Boolean policy."""
        require_exact(
            value=self.allow_reviewed_nonblocking_questions,
            expected=bool,
            field="Optional questions policy",
        )


@dataclass(frozen=True, kw_only=True)
class Publication:
    """The exact captured candidate, validation and release diagnostics."""

    id: PublicationId
    scope: ModelScope
    candidate: Candidate
    reference_pack: ReferencePack | None
    validation: ValidationReport
    readiness: Readiness
    changes: ChangeSet
    policy_fingerprint: str
    prepared_at: datetime

    def __post_init__(self) -> None:
        """Require all parts of the preparation to bind the same candidate."""
        require_exact(value=self.id, expected=PublicationId, field="Publication ID")
        require_exact(value=self.scope, expected=ModelScope, field="Publication scope")
        require_exact(value=self.candidate, expected=Candidate, field="Publication candidate")
        require_exact(
            value=self.validation, expected=ValidationReport, field="Publication validation"
        )
        require_exact(value=self.readiness, expected=Readiness, field="Publication readiness")
        require_exact(value=self.changes, expected=ChangeSet, field="Publication changes")
        if self.reference_pack is not None:
            require_exact(value=self.reference_pack, expected=ReferencePack, field="Reference pack")
        captured_pin = None if self.reference_pack is None else self.reference_pack.pin
        require_text(value=self.policy_fingerprint, field="Policy fingerprint")
        require_exact(value=self.prepared_at, expected=datetime, field="Preparation time")
        if self.prepared_at.utcoffset() is None:
            raise ValueError("Publication preparation requires an attributed time zone")
        if (
            self.scope != self.candidate.scope
            or self.scope != self.validation.scope
            or self.scope != self.readiness.scope
            or self.scope != self.changes.scope
            or self.candidate.id != self.validation.candidate_id
            or self.candidate.id != self.readiness.candidate_id
            or self.candidate.content_hash != self.validation.candidate_hash
            or self.candidate.content_hash != self.readiness.candidate_hash
            or self.candidate.reference_pack != self.validation.reference_pack
            or self.candidate.reference_pack != captured_pin
            or self.changes.after
            != CandidatePin(
                scope=self.scope,
                candidate_id=self.candidate.id,
                content_hash=self.candidate.content_hash,
            )
            or self.readiness.ready == bool(self.readiness.blockers)
        ):
            raise ValueError(
                "Publication snapshots must bind the same candidate, scope and outcomes"
            )

    @property
    def ready(self) -> bool:
        """Return readiness captured when the publication was prepared."""
        return self.readiness.ready

    @property
    def checks(self) -> tuple[ReadinessCheck, ...]:
        """Return the directly captured readiness checks."""
        return tuple(self.readiness.checks)

    @property
    def blockers(self) -> tuple[Issue, ...]:
        """Return the stored blockers for this exact preparation."""
        return tuple(self.readiness.blockers)

    @property
    def nonblocking_questions(self) -> tuple[VisibleQuestion, ...]:
        """Return the reviewed optional questions captured at preparation."""
        return tuple(self.readiness.nonblocking_questions)


@dataclass(frozen=True, kw_only=True)
class Approval:
    """Host attribution of authorization for one ready publication."""

    id: ApprovalId
    scope: ModelScope
    publication_id: PublicationId
    candidate_id: CandidateId
    candidate_hash: ContentHash
    validation_id: ValidationReportId
    workspace_revision: int
    review_snapshot_version: int
    policy_fingerprint: str
    actor: str
    reason: str
    approved_at: datetime

    def __post_init__(self) -> None:
        """Require strict captured identities, attribution and versions."""
        require_exact(value=self.id, expected=ApprovalId, field="Approval ID")
        require_exact(value=self.scope, expected=ModelScope, field="Approval scope")
        require_exact(value=self.publication_id, expected=PublicationId, field="Publication ID")
        require_exact(value=self.candidate_id, expected=CandidateId, field="Candidate ID")
        require_exact(value=self.candidate_hash, expected=ContentHash, field="Candidate hash")
        require_exact(value=self.validation_id, expected=ValidationReportId, field="Validation ID")
        require_exact(value=self.workspace_revision, expected=int, field="Workspace revision")
        require_exact(value=self.review_snapshot_version, expected=int, field="Review version")
        require_text(value=self.actor, field="Actor")
        require_text(value=self.reason, field="Approval reason")
        require_text(value=self.policy_fingerprint, field="Policy fingerprint")
        require_exact(value=self.approved_at, expected=datetime, field="Approval time")
        if self.workspace_revision < 0 or self.review_snapshot_version < 0:
            raise ValueError("Approval snapshot versions must be nonnegative")
        if self.approved_at.utcoffset() is None:
            raise ValueError("Approval time must include a time zone")


@dataclass(frozen=True, kw_only=True)
class DomainModelBundle:
    """An immutable model release and the exact authorization it retains."""

    id: BundleId
    scope: ModelScope
    version: str
    publication: Publication
    approval: Approval
    content_hash: ContentHash
    published_at: datetime
    schema_version: Literal["1.0"] = "1.0"
    semantic_mapping_version: Literal["1.0"] = "1.0"
    format: Literal["domain-kernel.bundle"] = "domain-kernel.bundle"

    def __post_init__(self) -> None:
        """Reject incompatible release, preparation and authorization snapshots."""
        require_exact(value=self.id, expected=BundleId, field="Bundle ID")
        require_exact(value=self.scope, expected=ModelScope, field="Bundle scope")
        require_text(value=self.version, field="Release version")
        require_exact(value=self.publication, expected=Publication, field="Publication")
        require_exact(value=self.approval, expected=Approval, field="Release approval")
        require_exact(value=self.content_hash, expected=ContentHash, field="Bundle hash")
        require_text(value=self.semantic_mapping_version, field="Semantic mapping version")
        if (self.schema_version, self.format, self.semantic_mapping_version) != (
            "1.0",
            "domain-kernel.bundle",
            "1.0",
        ):
            raise ValueError("Use the registered bundle format and schema version")
        require_exact(value=self.published_at, expected=datetime, field="Release time")
        if self.published_at.utcoffset() is None:
            raise ValueError("Release time must include a time zone")
        publication = self.publication
        approval = self.approval
        if (
            not publication.ready
            or self.scope != publication.scope
            or self.scope != approval.scope
            or approval.publication_id != publication.id
            or approval.candidate_id != publication.candidate.id
            or approval.candidate_hash != publication.candidate.content_hash
            or approval.validation_id != publication.validation.id
            or approval.workspace_revision != publication.candidate.workspace_revision
            or approval.review_snapshot_version != publication.candidate.review_snapshot_version
            or approval.policy_fingerprint != publication.policy_fingerprint
            or not publication.prepared_at <= approval.approved_at <= self.published_at
        ):
            raise ValueError("Bundle approval must authorize this exact ready preparation")

    @property
    def model_version(self) -> ModelVersion:
        """Return the exact scope, release label and content pin."""
        return ModelVersion(scope=self.scope, version=self.version, content_hash=self.content_hash)

    @property
    def kind(self) -> ModelKind:
        """Return the model intent captured in the release."""
        return self.publication.candidate.kind

    @property
    def description(self) -> str:
        """Return the captured description of the released model."""
        return self.publication.candidate.description

    @property
    def content(self) -> ModelContent:
        """Return the immutable content captured in the publication."""
        return self.publication.candidate.content

    def _definition(self, *, name: str | None, definition_id: DefinitionId | None) -> Definition:
        require_definition_selector(name=name, item_id=definition_id, id_type=DefinitionId)
        for definition in (*self.content.definitions, *self.content.retired_definitions):
            if definition.id == definition_id or definition.name == name:
                return definition
        raise DefinitionNotFoundError

    def get_concept(
        self,
        *,
        name: str | None = None,
        concept_id: DefinitionId | None = None,
    ) -> Concept:
        """Read one exact active or retired concept and its immutable children."""
        value = self._definition(name=name, definition_id=concept_id)
        inspected = typed_definition(value=value, body_type=ConceptDefinition, view_type=Concept)
        if not isinstance(inspected, Concept):
            raise DefinitionKindMismatchError
        return inspected

    def get_process(
        self,
        *,
        name: str | None = None,
        process_id: DefinitionId | None = None,
    ) -> Process:
        """Read one active or retired process and its exact immutable parts."""
        value = self._definition(name=name, definition_id=process_id)
        inspected = typed_definition(value=value, body_type=ProcessDefinition, view_type=Process)
        if not isinstance(inspected, Process):
            raise DefinitionKindMismatchError
        return inspected

    @classmethod
    def from_approved(
        cls,
        *,
        publication: Publication,
        approval: Approval,
        bundle_id: BundleId,
        version: str,
        now: datetime,
    ) -> DomainModelBundle:
        """Construct a release with exact approval and authored content bindings."""
        return cls(
            id=bundle_id,
            scope=publication.scope,
            version=version,
            publication=publication,
            approval=approval,
            published_at=now,
            content_hash=_bundle_codec().digest(
                bundle_id=bundle_id,
                version=version,
                publication=publication,
                approval=approval,
                released_at=now,
            ),
        )

    def serialize(self) -> bytes:
        """Return the canonical UTF-8 JSON bytes for this complete release."""
        return _bundle_codec().serialize(bundle=self)

    @classmethod
    def deserialize(
        cls,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> DomainModelBundle:
        """Independently verify and load a portable model release."""
        return _bundle_codec().deserialize(
            payload=payload, expected_hash=expected_hash, max_bytes=max_bytes
        )

    @classmethod
    def get_json_schema(cls, *, schema_version: str = "1.0") -> str:
        """Return the complete closed JSON Schema for the exact wire version."""
        return _bundle_codec().schema(version=schema_version)


@runtime_checkable
class _PortableBundleCodec(Protocol):
    def serialize(self, *, bundle: DomainModelBundle) -> bytes: ...

    def deserialize(
        self, *, payload: bytes | str, expected_hash: ContentHash | None, max_bytes: int
    ) -> DomainModelBundle: ...

    def schema(self, *, version: str) -> str: ...

    def digest(
        self,
        *,
        bundle_id: BundleId,
        version: str,
        publication: Publication,
        approval: Approval,
        released_at: datetime,
    ) -> ContentHash: ...


def _bundle_codec() -> _PortableBundleCodec:
    module = import_module("domain_kernel.bundles")
    # The codec imports these records to implement the portable format.
    codec: object = getattr(module, "PORTABLE_MODEL_CODEC", None)
    if not isinstance(codec, _PortableBundleCodec):
        raise TypeError("The built-in bundle codec is unavailable")
    return codec


@dataclass(frozen=True, kw_only=True)
class DependencyChange:
    """Complete old and target bundles captured under their own exact contexts."""

    request: DependencyChangeRequest
    before_bundles: Sequence[DomainModelBundle]
    after_bundles: Sequence[DomainModelBundle]
    affected_definition_ids: Sequence[DefinitionId]

    def __post_init__(self) -> None:
        """Freeze exact pins and affected local identities."""
        require_exact(value=self.request, expected=DependencyChangeRequest, field="Change request")
        for name, pins, bundles in (
            ("before_bundles", self.request.before, self.before_bundles),
            ("after_bundles", self.request.after, self.after_bundles),
        ):
            captured = snapshot_sequence(items=bundles, item_type=DomainModelBundle, field=name)
            if tuple(item.model_version for item in captured) != pins:
                raise ValueError("Retain both exact materialized dependency selections")
            object.__setattr__(self, name, captured)
        affected = snapshot_sequence(
            items=self.affected_definition_ids,
            item_type=DefinitionId,
            field="Affected identities",
        )
        if len(set(affected)) != len(affected):
            raise ValueError("Use distinct affected definition identities")
        object.__setattr__(self, "affected_definition_ids", affected)


@dataclass(frozen=True, kw_only=True)
class DecisionRecord:
    """Exact actor, inspected case version and committed effects for one decision."""

    id: DecisionId
    scope: ModelScope
    case_id: ReviewCaseId
    case_version: int
    action: ReviewAction
    actor: str
    recorded_at: datetime
    applied_changes: ChangeSet
    proposal_ids: tuple[ProposalId, ...] = ()
    supersedes_decision_id: DecisionId | None = None
    dependency_change: DependencyChange | None = field(
        default=None,
        metadata={"wire_omit_empty": True},
    )
    change_plan: ModelChangePlan | None = None
    group_decision_id: DecisionId | None = None
    member_decision_ids: tuple[DecisionId, ...] = ()
    generated_member_case_ids: tuple[ReviewCaseId, ...] = ()
    released_case_ids: tuple[ReviewCaseId, ...] = ()
