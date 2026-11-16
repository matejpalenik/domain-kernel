"""Domain Kernel's public SDK namespace."""

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.errors.project_not_found_error import ProjectNotFoundError
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.publication.domain.errors.publication_blocked_error import (
    PublicationBlockedError,
)
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.publication.domain.identifiers.publication_id import PublicationId
from domain_kernel.reconciliation.domain.identifiers.alignment_id import AlignmentId
from domain_kernel.reconciliation.domain.identifiers.alignment_suggestion_id import (
    AlignmentSuggestionId,
)
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId
from domain_kernel.reference_packs.domain.identifiers.pattern_id import PatternId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.enums.review_action_kind import ReviewActionKind
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.contracts import (
    CompanyDefinitionReference,
    Count,
    DefinitionReference,
    Issue,
    ModelScope,
    ModelVersion,
    Page,
    PinnedDefinitionReference,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import ConfigurationError, DomainKernelError, StaleStateError
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.identifiers.person_id import PersonId
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId


def hello() -> str:
    """Return the initial SDK greeting."""
    return "Hello from domain-kernel!"


__all__ = [
    "AlignmentId",
    "AlignmentSuggestionId",
    "ApprovalId",
    "AttributeId",
    "BundleId",
    "CandidateId",
    "CaseKind",
    "CaseStatus",
    "ChangePlanId",
    "CompanyDefinitionReference",
    "ConfigurationError",
    "ContentHash",
    "Count",
    "DecisionId",
    "DefinitionChangeKind",
    "DefinitionId",
    "DefinitionOrigin",
    "DefinitionReference",
    "DefinitionStatus",
    "DiscoveryDraftId",
    "DiscoveryRunId",
    "DomainKernelError",
    "EvidenceId",
    "InvalidDecisionError",
    "Issue",
    "IssueSeverity",
    "KeyId",
    "MappingId",
    "ModelId",
    "ModelNotFoundError",
    "ModelScope",
    "ModelVersion",
    "ObligationId",
    "Page",
    "PageCursor",
    "PatternId",
    "PersonId",
    "PinnedDefinitionReference",
    "ProjectId",
    "ProjectNotFoundError",
    "ProposalId",
    "PublicationBlockedError",
    "PublicationId",
    "QuestionId",
    "ReferenceDefinitionId",
    "ReviewActionKind",
    "ReviewCaseId",
    "SourceId",
    "SourceRevisionId",
    "StaleStateError",
    "ValidationReportId",
    "hello",
]
