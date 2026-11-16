"""Domain Kernel's public SDK namespace."""

from domain_kernel._shared.domain.data_shapes import (
    AttributeDefinition,
    AttributeType,
    ConceptReferenceType,
    ConstraintDefinition,
    ConstraintLanguage,
    ConstraintTarget,
    KeyDefinition,
    QuantityBinding,
    ScalarValueType,
    StructuredValueType,
    ValueSetType,
)
from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    DefinitionBody,
    EvidenceBasis,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
    ValueSetMember,
)
from domain_kernel._shared.domain.model_values import (
    BusinessCode,
    CardinalityBounds,
    CollectionKind,
    DataType,
    DecimalFacets,
    DecimalPrecision,
    DecimalScale,
    LabelRole,
    LabelText,
    LanguageTag,
    LocalizedDescription,
    LocalizedLabel,
    MeaningText,
    Nullability,
    RelationshipCardinality,
    ScalarDataType,
    Terminology,
    ValueSetMembership,
)
from domain_kernel._shared.domain.ontology_assets import (
    BlankNode,
    Iri,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyTermReference,
)
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.errors.attribute_already_exists_error import (
    AttributeAlreadyExistsError,
)
from domain_kernel.modeling.domain.errors.attribute_not_found_error import AttributeNotFoundError
from domain_kernel.modeling.domain.errors.key_already_exists_error import KeyAlreadyExistsError
from domain_kernel.modeling.domain.errors.key_not_found_error import KeyNotFoundError
from domain_kernel.modeling.domain.errors.model_already_exists_error import ModelAlreadyExistsError
from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.errors.project_already_exists_error import (
    ProjectAlreadyExistsError,
)
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
from domain_kernel.shared.errors import (
    ConfigurationError,
    DomainKernelError,
    MissingCapabilityError,
    StaleStateError,
)
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
    "AttributeAlreadyExistsError",
    "AttributeDefinition",
    "AttributeId",
    "AttributeNotFoundError",
    "AttributeType",
    "BlankNode",
    "BundleId",
    "BusinessCode",
    "CandidateId",
    "CardinalityBounds",
    "CaseKind",
    "CaseStatus",
    "ChangePlanId",
    "CollectionKind",
    "CompanyDefinitionReference",
    "Concept",
    "ConceptDefinition",
    "ConceptReferenceType",
    "ConfigurationError",
    "ConstraintDefinition",
    "ConstraintLanguage",
    "ConstraintTarget",
    "ContentHash",
    "Count",
    "DataType",
    "DecimalFacets",
    "DecimalPrecision",
    "DecimalScale",
    "DecisionId",
    "Definition",
    "DefinitionBody",
    "DefinitionChangeKind",
    "DefinitionId",
    "DefinitionKind",
    "DefinitionOrigin",
    "DefinitionReference",
    "DefinitionStatus",
    "DiscoveryDraftId",
    "DiscoveryRunId",
    "DomainKernelError",
    "EvidenceBasis",
    "EvidenceId",
    "InvalidDecisionError",
    "Iri",
    "Issue",
    "IssueSeverity",
    "KeyAlreadyExistsError",
    "KeyDefinition",
    "KeyId",
    "KeyNotFoundError",
    "LabelRole",
    "LabelText",
    "LanguageTag",
    "LocalizedDescription",
    "LocalizedLabel",
    "MappingId",
    "MeaningText",
    "MissingCapabilityError",
    "ModelAlreadyExistsError",
    "ModelId",
    "ModelKind",
    "ModelNotFoundError",
    "ModelScope",
    "ModelVersion",
    "Nullability",
    "ObligationId",
    "OntologyDocumentPin",
    "OntologyEntityKind",
    "OntologyTermReference",
    "Page",
    "PageCursor",
    "PatternId",
    "PersonId",
    "PinnedDefinitionReference",
    "ProjectAlreadyExistsError",
    "ProjectId",
    "ProjectNotFoundError",
    "ProposalId",
    "PublicationBlockedError",
    "PublicationId",
    "QuantityBinding",
    "QuestionId",
    "ReferenceDefinitionId",
    "RelationshipCardinality",
    "RelationshipDefinition",
    "ReviewActionKind",
    "ReviewCaseId",
    "ScalarDataType",
    "ScalarValueType",
    "SourceId",
    "SourceRevisionId",
    "StaleStateError",
    "StructuredValueDefinition",
    "StructuredValueType",
    "Terminology",
    "UnitDefinition",
    "ValidationReportId",
    "ValueSetDefinition",
    "ValueSetMember",
    "ValueSetMembership",
    "ValueSetType",
    "hello",
]
