"""Immutable compilation, validation and readiness records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.acceptance import AcceptanceCheckResult
from domain_kernel._shared.domain.changes import ReferenceDisposition, SourceAlignment
from domain_kernel._shared.domain.definitions import Definition
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.review.domain.models import DecisionRecord
from domain_kernel.shared.contracts import Issue, ModelScope, ModelVersion
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.review.domain.identifiers.decision_id import DecisionId


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
        if self.workspace_revision < 0 or self.review_snapshot_version < 0:
            raise ValueError("Snapshot versions are nonnegative")
        object.__setattr__(
            self,
            "dependencies",
            snapshot_sequence(
                items=self.dependencies, item_type=ModelVersion, field="Dependencies"
            ),
        )
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
