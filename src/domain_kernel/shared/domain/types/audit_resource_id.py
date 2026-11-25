"""Type contract for audit resource id."""

from __future__ import annotations

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
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId

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
