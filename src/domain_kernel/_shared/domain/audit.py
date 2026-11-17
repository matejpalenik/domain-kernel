"""Immutable attribution for durable SDK actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.artifacts import ProjectionMetadata
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import is_non_string_sequence, require_exact, require_text
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


@unique
class AuditAction(StrEnum):
    """Durable operations that receive their own attribution."""

    CREATE_PROJECT = "create_project"
    CREATE_MODEL = "create_model"
    INGEST_SOURCE = "ingest_source"
    INGEST_SOURCE_REVISION = "ingest_source_revision"
    CAPTURE_SOURCE_MANIFEST = "capture_source_manifest"
    PROFILE_SOURCE = "profile_source"
    COPY_SOURCE_ORIGINAL = "copy_source_original"
    DISCOVER = "discover"
    EXTRACT_PROPOSALS = "extract_proposals"
    RESUME_DISCOVERY = "resume_discovery"
    PROPOSE_ALIGNMENT = "propose_alignment"
    PROPOSE_CHANGE = "propose_change"
    REOPEN_REVIEW_CASE = "reopen_review_case"
    DECIDE_REVIEW = "decide_review"
    COMPILE = "compile"
    VALIDATE = "validate"
    PREPARE_PUBLICATION = "prepare_publication"
    PUBLISH = "publish"
    EXPORT = "export"


@unique
class AuditOutcome(StrEnum):
    """Recorded result of a durable action."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


type AuditResourceId = (
    ProjectId
    | ModelId
    | DefinitionId
    | SourceId
    | SourceRevisionId
    | SourceManifestId
    | EvidenceId
    | DiscoveryRunId
    | DiscoveryDraftId
    | AlignmentId
    | ChangePlanId
    | ReviewCaseId
    | DecisionId
    | CandidateId
    | ValidationReportId
    | PublicationId
    | ApprovalId
    | BundleId
)

AUDIT_RESOURCE_TYPES: tuple[type[AuditResourceId], ...] = (
    ProjectId,
    ModelId,
    DefinitionId,
    SourceId,
    SourceRevisionId,
    SourceManifestId,
    EvidenceId,
    DiscoveryRunId,
    DiscoveryDraftId,
    AlignmentId,
    ChangePlanId,
    ReviewCaseId,
    DecisionId,
    CandidateId,
    ValidationReportId,
    PublicationId,
    ApprovalId,
    BundleId,
)


@dataclass(frozen=True, kw_only=True)
class AuditResource:
    """Version or digest of an exact retained resource."""

    resource_id: AuditResourceId
    revision: int | None
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Require a recognized nominal resource and exact hash."""
        if type(self.resource_id) not in AUDIT_RESOURCE_TYPES:
            raise TypeError("Audit resources require a supported nominal resource identity")
        require_exact(value=self.content_hash, expected=ContentHash, field="Audit resource hash")
        if self.revision is not None:
            require_exact(value=self.revision, expected=int, field="Audit resource revision")
            if self.revision < 0:
                raise ValueError("Audit resource revision must be nonnegative")


@dataclass(frozen=True, kw_only=True)
class Artifact(ProjectionMetadata):
    """Identity and verified digest of a scoped external artifact."""

    project_id: ProjectId
    store: str
    key: str
    content_hash: ContentHash
    model_id: ModelId | None = None
    provider_version: str | None = None

    def __post_init__(self) -> None:
        """Validate the scope and exact artifact identity."""
        ProjectionMetadata.__post_init__(self)
        require_exact(value=self.project_id, expected=ProjectId, field="Artifact project")
        if self.model_id is not None:
            require_exact(value=self.model_id, expected=ModelId, field="Artifact model")
        require_exact(value=self.content_hash, expected=ContentHash, field="Artifact hash")
        require_text(value=self.store, field="Artifact store")
        require_text(value=self.key, field="Artifact key")
        if self.semantic is not None and (
            self.semantic.model.scope.project_id != self.project_id
            or self.semantic.model.scope.model_id != self.model_id
        ):
            raise ValueError("Use semantic metadata from the artifact's model scope")
        if self.schema is not None and (
            self.schema.model.scope.project_id != self.project_id
            or self.schema.model.scope.model_id != self.model_id
        ):
            raise ValueError("Use schema metadata from the artifact's model scope")
        if self.provider_version is not None:
            require_text(value=self.provider_version, field="Artifact provider version")


@dataclass(frozen=True, kw_only=True)
class AuditRecord:
    """An attributed snapshot of one durable action and its actual outcome."""

    id: AuditId
    project_id: ProjectId
    model_id: ModelId | None
    action: AuditAction
    outcome: AuditOutcome
    actor: str
    recorded_at: datetime
    before: Sequence[AuditResource | Artifact]
    after: Sequence[AuditResource | Artifact]
    reason: str | None = None
    parent_id: AuditId | None = None
    requested_artifact: Artifact | None = None

    def __post_init__(self) -> None:
        """Validate attribution and detach scoped effects from caller-owned inputs."""
        require_exact(value=self.id, expected=AuditId, field="Audit identity")
        require_exact(value=self.project_id, expected=ProjectId, field="Audit project")
        if self.model_id is not None:
            require_exact(value=self.model_id, expected=ModelId, field="Audit model")
        require_exact(value=self.action, expected=AuditAction, field="Audit action")
        require_exact(value=self.outcome, expected=AuditOutcome, field="Audit outcome")
        require_text(value=self.actor, field="Actor")
        if self.recorded_at.utcoffset() is None:
            raise ValueError("Audit time must include a time zone")
        if self.reason is not None:
            require_text(value=self.reason, field="Audit reason")
        if self.parent_id is not None:
            require_exact(value=self.parent_id, expected=AuditId, field="Parent audit identity")
            if self.parent_id == self.id:
                raise ValueError("An audit event cannot be its own parent")
        object.__setattr__(self, "before", self._effects(items=self.before))
        object.__setattr__(self, "after", self._effects(items=self.after))
        if self.requested_artifact is not None:
            require_exact(
                value=self.requested_artifact, expected=Artifact, field="Requested artifact"
            )
            self._check_scope(effect=self.requested_artifact)
        if self.outcome in (AuditOutcome.STARTED, AuditOutcome.FAILED) and any(
            type(effect) is Artifact for effect in self.after
        ):
            raise ValueError("An unfinished write cannot record a verified artifact")

    def _effects(
        self,
        *,
        items: Sequence[AuditResource | Artifact],
    ) -> tuple[AuditResource | Artifact, ...]:
        if not is_non_string_sequence(items):
            raise TypeError("Audit effects must be a sequence")
        effects = tuple(items)
        for effect in effects:
            if type(effect) not in (AuditResource, Artifact):
                raise TypeError("Audit effects must be typed resources or artifacts")
            self._check_scope(effect=effect)
        return effects

    def _check_scope(self, *, effect: AuditResource | Artifact) -> None:
        if isinstance(effect, Artifact):
            if effect.project_id != self.project_id or effect.model_id != self.model_id:
                raise ValueError("Artifact does not belong to this audit scope")
        elif (type(effect.resource_id) is ProjectId and effect.resource_id != self.project_id) or (
            type(effect.resource_id) is ModelId and effect.resource_id != self.model_id
        ):
            raise ValueError("Resource does not belong to this audit scope")
