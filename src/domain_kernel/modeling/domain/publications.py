"""Immutable publication preparation, authorization and release values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.changes import ChangeSet
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.snapshots import Candidate, Readiness, ValidationReport
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.shared.contracts import CandidatePin, ModelScope
from domain_kernel.shared.errors import ScopeMismatchError, StaleStateError
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.snapshots import (
        ReadinessCheck,
        VisibleQuestion,
    )
    from domain_kernel.shared.contracts import Issue


@dataclass(frozen=True, kw_only=True)
class Publication:
    """The exact captured candidate, validation and release diagnostics."""

    id: PublicationId
    scope: ModelScope
    candidate: Candidate
    reference_pack: None
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
        require_exact(value=self.reference_pack, expected=type(None), field="Reference pack")
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


def require_current_publication(
    *,
    publication: Publication,
    current: Candidate,
    policy_fingerprint: str,
) -> None:
    """Require unchanged workspace, review state and rules at authorization."""
    if publication.scope != current.scope:
        raise ScopeMismatchError
    stored = publication.candidate
    if (
        current.workspace_revision != stored.workspace_revision
        or current.review_snapshot_version != stored.review_snapshot_version
        or current.review_snapshot_hash != stored.review_snapshot_hash
        or current.content_hash != stored.content_hash
        or policy_fingerprint != publication.policy_fingerprint
    ):
        raise StaleStateError(message="Prepare and inspect a fresh publication for this workspace")
