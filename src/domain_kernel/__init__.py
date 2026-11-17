"""Domain Kernel's public SDK namespace."""

from typing import TYPE_CHECKING

from domain_kernel._shared.application.inference import ModelGateway
from domain_kernel._shared.domain.acceptance import (
    AcceptanceCheckDefinition,
    AcceptanceCheckResult,
    AcceptancePredicate,
    CheckOutcome,
    CheckRequirement,
    DistinctDefinitionsCheck,
    ManualCriterion,
    QuantityRequiredCheck,
)
from domain_kernel._shared.domain.audit import (
    Artifact,
    AuditAction,
    AuditOutcome,
    AuditRecord,
    AuditResource,
)
from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    IncludeCase,
    ModelChangePlan,
    PlannedOperation,
    RestoreDefinition,
    RetireDefinition,
    ReviseDefinition,
)
from domain_kernel._shared.domain.business_decisions import (
    BusinessDecisionDefinition,
    DecisionInput,
    DecisionOutput,
    DecisionRule,
    DecisionValue,
    HitPolicy,
    RuleDefinition,
)
from domain_kernel._shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    DefinitionChange,
)
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
    Process,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
    ValueSetMember,
)
from domain_kernel._shared.domain.dependency_requests import (
    DependencyChangeRequest,
    DependencyRemapping,
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
from domain_kernel._shared.domain.process_parts import (
    Activity,
    Condition,
    Event,
    EventKind,
    Flow,
    FlowKind,
    Gateway,
    GatewayDirection,
    GatewayKind,
    ProcessNodeId,
    Role,
)
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel.authoring import UNSET, DomainModelBuilder, Unset
from domain_kernel.bundles import BundleValidation, DomainModelBundle, validate_bundle
from domain_kernel.composition import compose_models, slice_model
from domain_kernel.diagnostics import (
    ConfigurationReport,
    ConfigurationSetting,
    ConfigurationSource,
    DatabaseInitialization,
)
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.api.model import Model
from domain_kernel.modeling.domain.composition import (
    ModelComposition,
    ModelSlice,
    SliceDefinition,
    TraversalDirection,
)
from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.errors.attribute_already_exists_error import (
    AttributeAlreadyExistsError,
)
from domain_kernel.modeling.domain.errors.attribute_not_found_error import AttributeNotFoundError
from domain_kernel.modeling.domain.errors.definition_errors import (
    DefinitionAlreadyExistsError,
    DefinitionKindMismatchError,
    DefinitionNotFoundError,
)
from domain_kernel.modeling.domain.errors.key_already_exists_error import KeyAlreadyExistsError
from domain_kernel.modeling.domain.errors.key_not_found_error import KeyNotFoundError
from domain_kernel.modeling.domain.errors.model_already_exists_error import ModelAlreadyExistsError
from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.flow_id import FlowId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.modeling.domain.models import ModelInfo, ReferencePackPin
from domain_kernel.modeling.domain.publications import Approval, Publication
from domain_kernel.modeling.domain.snapshots import (
    Candidate,
    DependencyChange,
    ModelContent,
    PublicationRules,
    Readiness,
    ReadinessCheck,
    ReviewSnapshot,
    ValidationReport,
    VisibleQuestion,
)
from domain_kernel.projects.domain.errors.project_already_exists_error import (
    ProjectAlreadyExistsError,
)
from domain_kernel.projects.domain.errors.project_not_found_error import ProjectNotFoundError
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.projects.domain.project_info import ProjectInfo
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
from domain_kernel.reference_packs.api.packs import (
    ReferencePack,
    ReferencePackBuild,
    ReferencePackImport,
    ReferencePackSpec,
)
from domain_kernel.reference_packs.domain.contracts import (
    DefinitionBinding,
    MappingRelation,
    ObligationKind,
    PackMaturity,
    Pattern,
    PatternAdoption,
    ReferenceAlignment,
    ReferenceAssetKind,
    ReferenceDefinition,
    ReferenceOrigin,
    ReferencePackComposition,
    ReferencePackDependency,
    ReferencePackImportManifest,
    ReferencePackObligation,
    ReferencePackValidation,
)
from domain_kernel.reference_packs.domain.identifiers.pattern_id import PatternId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.decisions import (
    Accept,
    ApproveLocalExtension,
    EditDefinition,
    MapToReference,
    Reject,
    ReviewAction,
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
from domain_kernel.review.domain.models import (
    CaseDecision,
    DecisionRecord,
    ReviewCase,
    ReviewImpact,
    ReviewReceipt,
)
from domain_kernel.shared.contracts import (
    CandidatePin,
    CompanyDefinitionReference,
    Count,
    DefinitionReference,
    Issue,
    ModelScope,
    ModelVersion,
    Page,
    PinnedDefinitionReference,
    SnapshotReference,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import (
    ConfigurationError,
    DomainKernelError,
    IdempotencyConflictError,
    InvalidBundleError,
    InvalidReferencePackError,
    MissingCapabilityError,
    OperationInProgressError,
    PatternNotFoundError,
    ProcessPartAlreadyExistsError,
    ProcessPartNotFoundError,
    PublicationNotFoundError,
    ReferencePackNotFoundError,
    ResourceLimitError,
    ScopeMismatchError,
    SourceNotFoundError,
    SourceReadError,
    StaleStateError,
    UnsupportedBundleVersionError,
    UnsupportedReferencePackVersionError,
    VersionExistsError,
)
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.identifiers.person_id import PersonId
from domain_kernel.sources.domain.errors.source_already_exists_error import SourceAlreadyExistsError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.models import (
    FileOrigin,
    IngestedSource,
    OriginalCopy,
    ProcessingLimits,
    ProcessingRecord,
    Source,
    SourceProfile,
    SourceRevision,
)

if TYPE_CHECKING:
    from domain_kernel._composition import ClientIntegrations
    from domain_kernel.client import Client
    from domain_kernel.configuration import ClientConfiguration
    from domain_kernel.project import Project
    from domain_kernel.sources.application.contracts import (
        CSV,
        PDF,
        BatchIngestionResult,
        CopyTo,
        Excel,
        FileDescriptor,
        FileInput,
        IngestionFailure,
        IngestionStage,
        IngestionSuccess,
        Ontology,
        ReaderLocation,
        SourceDescriptor,
        SourceEntry,
        SourceEntryKind,
        SourceFolder,
        SourceInput,
        Word,
    )
    from domain_kernel.sources.application.ports import (
        AcquiredSource,
        FormatParser,
        OriginalStore,
        ParsedChunk,
        SourceReader,
    )


_SOURCE_DESCRIPTORS = frozenset(
    {
        "CSV",
        "PDF",
        "BatchIngestionResult",
        "CopyTo",
        "Excel",
        "FileDescriptor",
        "FileInput",
        "IngestionFailure",
        "IngestionStage",
        "IngestionSuccess",
        "Ontology",
        "ReaderLocation",
        "SourceDescriptor",
        "SourceEntry",
        "SourceEntryKind",
        "SourceFolder",
        "SourceInput",
        "Word",
    }
)
_SOURCE_PORTS = frozenset(
    {"AcquiredSource", "FormatParser", "OriginalStore", "ParsedChunk", "SourceReader"}
)


def __getattr__(name: str) -> object:
    """Load the configuration entry points when requested."""
    if name == "Client":
        from domain_kernel.client import Client  # noqa: PLC0415 - Preserve lightweight root imports.

        return Client
    if name == "ClientIntegrations":
        from domain_kernel._composition import ClientIntegrations  # noqa: PLC0415

        return ClientIntegrations
    if name == "ClientConfiguration":
        from domain_kernel.configuration import ClientConfiguration  # noqa: PLC0415

        return ClientConfiguration
    if name == "Project":
        from domain_kernel.project import Project  # noqa: PLC0415

        return Project
    if name in _SOURCE_DESCRIPTORS:
        from domain_kernel.sources.application import contracts  # noqa: PLC0415 - Lazy settings.

        exported: object = getattr(contracts, name, None)
        return exported
    if name in _SOURCE_PORTS:
        from domain_kernel.sources.application import ports  # noqa: PLC0415 - Lazy host ports.

        capability: object = getattr(ports, name, None)
        return capability
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)


def hello() -> str:
    """Return the initial SDK greeting."""
    return "Hello from domain-kernel!"


__all__ = [
    "CSV",
    "PDF",
    "UNSET",
    "Accept",
    "AcceptanceCheckDefinition",
    "AcceptanceCheckResult",
    "AcceptancePredicate",
    "AcquiredSource",
    "Activity",
    "ActivityId",
    "AlignmentId",
    "AlignmentSuggestionId",
    "Approval",
    "ApprovalId",
    "ApproveLocalExtension",
    "Artifact",
    "AttributeAlreadyExistsError",
    "AttributeDefinition",
    "AttributeId",
    "AttributeNotFoundError",
    "AttributeType",
    "AuditAction",
    "AuditId",
    "AuditOutcome",
    "AuditRecord",
    "AuditResource",
    "AuthoredContent",
    "BatchIngestionResult",
    "BlankNode",
    "BundleId",
    "BundleValidation",
    "BusinessCode",
    "BusinessDecisionDefinition",
    "Candidate",
    "CandidateId",
    "CandidatePin",
    "CardinalityBounds",
    "CaseDecision",
    "CaseKind",
    "CaseStatus",
    "ChangePlanId",
    "ChangeSet",
    "CheckOutcome",
    "CheckRequirement",
    "Client",
    "ClientConfiguration",
    "ClientIntegrations",
    "CollectionKind",
    "CompanyDefinitionReference",
    "ComparisonKind",
    "Compatibility",
    "Concept",
    "ConceptDefinition",
    "ConceptReferenceType",
    "Condition",
    "ConditionId",
    "ConfigurationError",
    "ConfigurationReport",
    "ConfigurationSetting",
    "ConfigurationSource",
    "ConstraintDefinition",
    "ConstraintLanguage",
    "ConstraintTarget",
    "ContentHash",
    "CopyTo",
    "Count",
    "CreateDefinition",
    "DataType",
    "DatabaseInitialization",
    "DecimalFacets",
    "DecimalPrecision",
    "DecimalScale",
    "DecisionId",
    "DecisionInput",
    "DecisionOutput",
    "DecisionRecord",
    "DecisionRule",
    "DecisionValue",
    "Definition",
    "DefinitionAlreadyExistsError",
    "DefinitionBinding",
    "DefinitionBody",
    "DefinitionChange",
    "DefinitionChangeKind",
    "DefinitionId",
    "DefinitionKind",
    "DefinitionKindMismatchError",
    "DefinitionNotFoundError",
    "DefinitionOrigin",
    "DefinitionReference",
    "DefinitionStatus",
    "DependencyChange",
    "DependencyChangeRequest",
    "DependencyRemapping",
    "DiscoveryDraftId",
    "DiscoveryRunId",
    "DistinctDefinitionsCheck",
    "DomainKernelError",
    "DomainModelBuilder",
    "DomainModelBundle",
    "EditDefinition",
    "Event",
    "EventId",
    "EventKind",
    "EvidenceBasis",
    "EvidenceId",
    "Excel",
    "FileDescriptor",
    "FileInput",
    "FileOrigin",
    "Flow",
    "FlowId",
    "FlowKind",
    "FormatParser",
    "Gateway",
    "GatewayDirection",
    "GatewayId",
    "GatewayKind",
    "HitPolicy",
    "IdempotencyConflictError",
    "IncludeCase",
    "IngestedSource",
    "IngestionFailure",
    "IngestionStage",
    "IngestionSuccess",
    "InvalidBundleError",
    "InvalidDecisionError",
    "InvalidReferencePackError",
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
    "ManualCriterion",
    "MapToReference",
    "MappingId",
    "MappingRelation",
    "MeaningText",
    "MissingCapabilityError",
    "Model",
    "ModelAlreadyExistsError",
    "ModelChangePlan",
    "ModelComposition",
    "ModelContent",
    "ModelGateway",
    "ModelId",
    "ModelInfo",
    "ModelKind",
    "ModelNotFoundError",
    "ModelScope",
    "ModelSlice",
    "ModelVersion",
    "Nullability",
    "ObligationId",
    "ObligationKind",
    "Ontology",
    "OntologyDocumentPin",
    "OntologyEntityKind",
    "OntologyTermReference",
    "OperationInProgressError",
    "OriginalCopy",
    "OriginalStore",
    "PackMaturity",
    "Page",
    "PageCursor",
    "ParsedChunk",
    "Pattern",
    "PatternAdoption",
    "PatternId",
    "PatternNotFoundError",
    "PersonId",
    "PinnedDefinitionReference",
    "PlannedOperation",
    "Process",
    "ProcessDefinition",
    "ProcessNodeId",
    "ProcessPartAlreadyExistsError",
    "ProcessPartNotFoundError",
    "ProcessingLimits",
    "ProcessingRecord",
    "Project",
    "ProjectAlreadyExistsError",
    "ProjectId",
    "ProjectInfo",
    "ProjectNotFoundError",
    "ProposalId",
    "Publication",
    "PublicationBlockedError",
    "PublicationId",
    "PublicationNotFoundError",
    "PublicationRules",
    "QuantityBinding",
    "QuantityRequiredCheck",
    "QuestionId",
    "ReaderLocation",
    "Readiness",
    "ReadinessCheck",
    "ReferenceAlignment",
    "ReferenceAssetKind",
    "ReferenceDefinition",
    "ReferenceDefinitionId",
    "ReferenceOrigin",
    "ReferencePack",
    "ReferencePackBuild",
    "ReferencePackComposition",
    "ReferencePackDependency",
    "ReferencePackImport",
    "ReferencePackImportManifest",
    "ReferencePackNotFoundError",
    "ReferencePackObligation",
    "ReferencePackPin",
    "ReferencePackSpec",
    "ReferencePackValidation",
    "Reject",
    "RelationshipCardinality",
    "RelationshipDefinition",
    "ResourceLimitError",
    "RestoreDefinition",
    "RetireDefinition",
    "ReviewAction",
    "ReviewActionKind",
    "ReviewCase",
    "ReviewCaseId",
    "ReviewImpact",
    "ReviewReceipt",
    "ReviewSnapshot",
    "ReviseDefinition",
    "Role",
    "RoleId",
    "RuleDefinition",
    "ScalarDataType",
    "ScalarValueType",
    "ScopeMismatchError",
    "SliceDefinition",
    "SnapshotReference",
    "Source",
    "SourceAlreadyExistsError",
    "SourceDescriptor",
    "SourceEntry",
    "SourceEntryKind",
    "SourceFolder",
    "SourceId",
    "SourceInput",
    "SourceManifestId",
    "SourceNotFoundError",
    "SourceProfile",
    "SourceReadError",
    "SourceReader",
    "SourceRevision",
    "SourceRevisionId",
    "SourceRevisionMismatchError",
    "StaleStateError",
    "StructuredValueDefinition",
    "StructuredValueType",
    "Terminology",
    "TraversalDirection",
    "UnitDefinition",
    "Unset",
    "UnsupportedBundleVersionError",
    "UnsupportedReferencePackVersionError",
    "ValidationReport",
    "ValidationReportId",
    "ValueSetDefinition",
    "ValueSetMember",
    "ValueSetMembership",
    "ValueSetType",
    "VersionExistsError",
    "VisibleQuestion",
    "Word",
    "compose_models",
    "hello",
    "slice_model",
    "validate_bundle",
]
