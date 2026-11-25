"""Domain Kernel's public SDK namespace."""

from importlib import import_module
from typing import TYPE_CHECKING

from domain_kernel.authoring import UNSET, DomainModelBuilder, Unset
from domain_kernel.bundles import BundleValidation, DomainModelBundle, validate_bundle
from domain_kernel.composition import compose_models, slice_model
from domain_kernel.diagnostics import (
    ConfigurationReport,
    ConfigurationSetting,
    ConfigurationSource,
    DatabaseInitialization,
)
from domain_kernel.discovery.domain.bindings import (
    BindingWitness,
    EndpointBinding,
    HeldRelationship,
    RelationshipBinding,
)
from domain_kernel.discovery.domain.coverage import (
    DiscoveryCoverage,
    DiscoveryWindow,
)
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.discovery_draft_id import DiscoveryDraftId
from domain_kernel.discovery.domain.identifiers.discovery_run_id import DiscoveryRunId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.discovery.domain.models import (
    DiscoveryDraft,
    DiscoveryFailure,
    DiscoveryProgress,
    DiscoveryPrompt,
    DiscoveryResult,
    ExtractionProvenance,
    InterpretationContext,
    Proposal,
    RunStatus,
)
from domain_kernel.discovery.domain.schema_options import (
    CompetencyQuestion,
    DiscoverySourceContext,
    SchemaDiscoveryOptions,
)
from domain_kernel.interchange import load_linkml, project_linkml, project_semantics
from domain_kernel.modeling.api.model import Model
from domain_kernel.modeling.application.ontology import (
    OntologyAdapter,
    OntologyModuleExtractor,
    OntologyReasoner,
)
from domain_kernel.modeling.application.ontology_validation import ReasoningModelValidator
from domain_kernel.modeling.application.validation_ports import SemanticValidator
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
from domain_kernel.modeling.domain.interchange import (
    IdentityBinding,
    JsonSchemaProjectionRequest,
    LinkmlProjectionRequest,
    LinkmlSyntax,
    MappingDescriptor,
    ProjectionAssessment,
    ProjectionAvailability,
    ProjectionBlockedError,
    ProjectionFeature,
    ProjectionFinding,
    ProjectionLocation,
    ProjectionRemedy,
    ProjectionRequest,
    RdfProjectionRequest,
    RdfSyntax,
    RepresentationSupport,
    SemanticDocument,
    SemanticOntologyDependency,
    SemanticProjection,
    UnitAnnotation,
    UnitBindingAnnotation,
    ValidationGraphs,
    ValidationResponsibility,
)
from domain_kernel.modeling.domain.linkml import (
    InvalidSchemaError,
    LinkmlProjection,
    OpenValueSetAnnotation,
    SchemaDocument,
    SchemaImportResult,
)
from domain_kernel.modeling.domain.models import ModelInfo, ReferencePackPin
from domain_kernel.modeling.domain.process import Process
from domain_kernel.modeling.domain.publications import Approval, Publication
from domain_kernel.modeling.domain.semantics import (
    OntologyModuleResult,
    ReasoningRequest,
    ReasoningResult,
)
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
from domain_kernel.modeling.infrastructure.shacl_validation import ShaclModelValidator
from domain_kernel.ontologies import (
    extract_ontology_module,
    load_ontology,
    reason_ontology,
    serialize_ontology,
    transcode_ontology,
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
from domain_kernel.reconciliation.domain.models import (
    Alignment,
    AlignmentLayer,
    AlignmentStatus,
    AlignmentSuggestion,
)
from domain_kernel.reference_packs.api.packs import (
    ReferencePack,
    ReferencePackBuild,
    ReferencePackImport,
    ReferencePackSpec,
)
from domain_kernel.reference_packs.domain.changes import ReferencePackChange
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
from domain_kernel.review.api.review import ConfirmStatement
from domain_kernel.review.domain.decisions import (
    Accept,
    AnswerQuestion,
    ApproveLocalExtension,
    Confirmation,
    ConfirmationMethod,
    Defer,
    EditDefinition,
    Exclude,
    KeepNonblockingQuestion,
    MapToDefinition,
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
from domain_kernel.review.domain.questions import (
    Question,
    QuestionDisposition,
    RequirementKind,
    ReviewRequirement,
)
from domain_kernel.shared.application.artifacts import ArtifactStore, ArtifactWrite, ExportPayload
from domain_kernel.shared.application.inference import (
    InferenceInput,
    ModelGateway,
    ModelRequest,
    ModelResponse,
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
from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.entities.concept import Concept
from domain_kernel.shared.domain.entities.condition import Condition
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.entities.event import Event
from domain_kernel.shared.domain.entities.flow import Flow
from domain_kernel.shared.domain.entities.gateway import Gateway
from domain_kernel.shared.domain.entities.key_definition import KeyDefinition
from domain_kernel.shared.domain.entities.model_change_plan import ModelChangePlan
from domain_kernel.shared.domain.entities.role import Role
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.enums.check_outcome import CheckOutcome
from domain_kernel.shared.domain.enums.check_requirement import CheckRequirement
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.comparison_kind import ComparisonKind
from domain_kernel.shared.domain.enums.compatibility import Compatibility
from domain_kernel.shared.domain.enums.constraint_language import ConstraintLanguage
from domain_kernel.shared.domain.enums.constraint_target import ConstraintTarget
from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.enums.event_kind import EventKind
from domain_kernel.shared.domain.enums.evidence_basis import EvidenceBasis
from domain_kernel.shared.domain.enums.flow_kind import FlowKind
from domain_kernel.shared.domain.enums.gateway_direction import GatewayDirection
from domain_kernel.shared.domain.enums.gateway_kind import GatewayKind
from domain_kernel.shared.domain.enums.hit_policy import HitPolicy
from domain_kernel.shared.domain.enums.label_role import LabelRole
from domain_kernel.shared.domain.enums.module_extraction_method import ModuleExtractionMethod
from domain_kernel.shared.domain.enums.module_guarantee import ModuleGuarantee
from domain_kernel.shared.domain.enums.nullability import Nullability
from domain_kernel.shared.domain.enums.ontology_entity_kind import OntologyEntityKind
from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
from domain_kernel.shared.domain.enums.reasoning_profile import ReasoningProfile
from domain_kernel.shared.domain.enums.reasoning_task import ReasoningTask
from domain_kernel.shared.domain.enums.semantic_graph_role import SemanticGraphRole
from domain_kernel.shared.domain.enums.semantic_regime import SemanticRegime
from domain_kernel.shared.domain.enums.semantic_relation import SemanticRelation
from domain_kernel.shared.domain.enums.semantic_status import SemanticStatus
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.enums.value_set_membership import ValueSetMembership
from domain_kernel.shared.domain.errors.artifact_conflict_error import ArtifactConflictError
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.errors.missing_dependency_error import MissingDependencyError
from domain_kernel.shared.domain.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)
from domain_kernel.shared.domain.operations.correct_mapping import CorrectMapping
from domain_kernel.shared.domain.operations.create_definition import CreateDefinition
from domain_kernel.shared.domain.operations.include_case import IncludeCase
from domain_kernel.shared.domain.operations.map_to_planned_definition import MapToPlannedDefinition
from domain_kernel.shared.domain.operations.restore_definition import RestoreDefinition
from domain_kernel.shared.domain.operations.retire_definition import RetireDefinition
from domain_kernel.shared.domain.operations.revise_definition import ReviseDefinition
from domain_kernel.shared.domain.types.acceptance_predicate import AcceptancePredicate
from domain_kernel.shared.domain.types.attribute_type import AttributeType
from domain_kernel.shared.domain.types.consumer_obligation import ConsumerObligation
from domain_kernel.shared.domain.types.definition_body import DefinitionBody
from domain_kernel.shared.domain.types.mapping_correction_action import MappingCorrectionAction
from domain_kernel.shared.domain.types.planned_operation import PlannedOperation
from domain_kernel.shared.domain.types.process_node_id import ProcessNodeId
from domain_kernel.shared.domain.types.scalar_data_type import ScalarDataType
from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.domain.value_objects.acceptance_check_result import AcceptanceCheckResult
from domain_kernel.shared.domain.value_objects.attribute_equals import AttributeEquals
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.domain.value_objects.authored_content import AuthoredContent
from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.business_code import BusinessCode
from domain_kernel.shared.domain.value_objects.business_decision_definition import (
    BusinessDecisionDefinition,
)
from domain_kernel.shared.domain.value_objects.cardinality_bounds import CardinalityBounds
from domain_kernel.shared.domain.value_objects.cardinality_rule import CardinalityRule
from domain_kernel.shared.domain.value_objects.change_set import ChangeSet
from domain_kernel.shared.domain.value_objects.collection_semantics_obligation import (
    CollectionSemanticsObligation,
)
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.concept_reference_type import ConceptReferenceType
from domain_kernel.shared.domain.value_objects.constraint_definition import ConstraintDefinition
from domain_kernel.shared.domain.value_objects.decimal_facets import DecimalFacets
from domain_kernel.shared.domain.value_objects.decimal_precision import DecimalPrecision
from domain_kernel.shared.domain.value_objects.decimal_scale import DecimalScale
from domain_kernel.shared.domain.value_objects.decision_input import DecisionInput
from domain_kernel.shared.domain.value_objects.decision_output import DecisionOutput
from domain_kernel.shared.domain.value_objects.decision_rule import DecisionRule
from domain_kernel.shared.domain.value_objects.decision_value import DecisionValue
from domain_kernel.shared.domain.value_objects.definition_change import DefinitionChange
from domain_kernel.shared.domain.value_objects.dependency_change_request import (
    DependencyChangeRequest,
)
from domain_kernel.shared.domain.value_objects.dependency_remapping import DependencyRemapping
from domain_kernel.shared.domain.value_objects.distinct_definitions_check import (
    DistinctDefinitionsCheck,
)
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.key_enforcement_obligation import (
    KeyEnforcementObligation,
)
from domain_kernel.shared.domain.value_objects.label_text import LabelText
from domain_kernel.shared.domain.value_objects.language_tag import LanguageTag
from domain_kernel.shared.domain.value_objects.localized_description import LocalizedDescription
from domain_kernel.shared.domain.value_objects.localized_label import LocalizedLabel
from domain_kernel.shared.domain.value_objects.manual_criterion import ManualCriterion
from domain_kernel.shared.domain.value_objects.meaning_text import MeaningText
from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference
from domain_kernel.shared.domain.value_objects.module_extraction_support import (
    ModuleExtractionSupport,
)
from domain_kernel.shared.domain.value_objects.ontology_capabilities import OntologyCapabilities
from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
from domain_kernel.shared.domain.value_objects.ontology_closure_pin import OntologyClosurePin
from domain_kernel.shared.domain.value_objects.ontology_context_binding import (
    OntologyContextBinding,
)
from domain_kernel.shared.domain.value_objects.ontology_document import OntologyDocument
from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.domain.value_objects.ontology_import_binding import OntologyImportBinding
from domain_kernel.shared.domain.value_objects.ontology_limits import OntologyLimits
from domain_kernel.shared.domain.value_objects.ontology_module_definition import (
    OntologyModuleDefinition,
)
from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference
from domain_kernel.shared.domain.value_objects.parsed_ontology import ParsedOntology
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.domain.value_objects.quantity_binding import QuantityBinding
from domain_kernel.shared.domain.value_objects.quantity_required_check import QuantityRequiredCheck
from domain_kernel.shared.domain.value_objects.rdf_literal import RdfLiteral
from domain_kernel.shared.domain.value_objects.reasoning_support import ReasoningSupport
from domain_kernel.shared.domain.value_objects.reference_target_obligation import (
    ReferenceTargetObligation,
)
from domain_kernel.shared.domain.value_objects.relation_type_ref import RelationTypeRef
from domain_kernel.shared.domain.value_objects.relationship_cardinality import (
    RelationshipCardinality,
)
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.domain.value_objects.relationship_enforcement_obligation import (
    RelationshipEnforcementObligation,
)
from domain_kernel.shared.domain.value_objects.rule_definition import RuleDefinition
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.schema_artifact_metadata import (
    SchemaArtifactMetadata,
)
from domain_kernel.shared.domain.value_objects.schema_origin import SchemaOrigin
from domain_kernel.shared.domain.value_objects.semantic_artifact_metadata import (
    SemanticArtifactMetadata,
)
from domain_kernel.shared.domain.value_objects.semantic_link_definition import (
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment
from domain_kernel.shared.domain.value_objects.source_alignment_change import SourceAlignmentChange
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_type import StructuredValueType
from domain_kernel.shared.domain.value_objects.terminology import Terminology
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition
from domain_kernel.shared.domain.value_objects.value_set_member import ValueSetMember
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.errors import (
    ConfigurationError,
    DomainKernelError,
    IdempotencyConflictError,
    InferenceError,
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
from domain_kernel.sources.domain.coverage import CoverageStatus, CoverageUnit
from domain_kernel.sources.domain.document_formats import DocumentFormat
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.errors.source_already_exists_error import SourceAlreadyExistsError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.errors.source_unavailable_error import SourceUnavailableError
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_manifest_id import SourceManifestId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.models import (
    Evidence,
    EvidenceContent,
    FileOrigin,
    IngestedSource,
    Origin,
    OriginalCopy,
    ProcessingLimits,
    ProcessingRecord,
    Source,
    SourceProfile,
    SourceRevision,
)
from domain_kernel.sources.domain.parsed import (
    CellRange,
    CellValue,
    DocumentSpan,
    EvidenceLocator,
    ExternalLocation,
    ParsedGraph,
    ParsedPart,
    ParsedPayload,
    ParsedSourceOrigin,
    ParsedTable,
    ParsedText,
    StatementSpan,
)
from domain_kernel.sources.domain.statements import (
    Person,
    StatementForm,
    StatementIntent,
    StatementOrigin,
)
from domain_kernel.sources.domain.tables import ColumnProfile, InferredColumnType, TableProfile

if TYPE_CHECKING:
    from domain_kernel._composition import ClientIntegrations
    from domain_kernel.client import Client
    from domain_kernel.configuration import ClientConfiguration
    from domain_kernel.discovery.infrastructure.langgraph_gateway import (
        DiscoveryStage,
        DiscoveryStageRoute,
        LangGraphDiscoveryGateway,
    )
    from domain_kernel.discovery.infrastructure.litellm_gateway import LiteLLMGateway
    from domain_kernel.discovery.infrastructure.local_replay import LocalReplayGateway
    from domain_kernel.discovery.infrastructure.mentions import NamedEntityHints
    from domain_kernel.notebook import (
        NotebookRenderer,
        NotebookValue,
        disable_notebook_display,
        enable_notebook_display,
        render_notebook,
    )
    from domain_kernel.project import Project
    from domain_kernel.reconciliation.infrastructure.similarity import RapidFuzzSimilarityScorer
    from domain_kernel.sources.application.contracts import (
        CSV,
        PDF,
        BatchIngestionResult,
        CopyTo,
        Document,
        Excel,
        FileDescriptor,
        FileInput,
        IngestionFailure,
        IngestionStage,
        IngestionSuccess,
        Ontology,
        ParsedSource,
        ReaderLocation,
        SourceDescriptor,
        SourceEntry,
        SourceEntryKind,
        SourceFolder,
        SourceInput,
        Statement,
        Word,
    )
    from domain_kernel.sources.application.ports import (
        AcquiredSource,
        FormatParser,
        OriginalStore,
        ParsedChunk,
        ParsedSourceProvider,
        ParsedSourceResolver,
        SourceReader,
    )
    from domain_kernel.sources.infrastructure.aws import (
        AwsCredentialProvider,
        AwsCredentialSnapshot,
    )
    from domain_kernel.sources.infrastructure.docling_documents import DoclingParser
    from domain_kernel.sources.infrastructure.entra import EntraClientCredentials
    from domain_kernel.sources.infrastructure.s3_reader import S3ReaderAdapter
    from domain_kernel.sources.infrastructure.s3_store import S3ArtifactStore, S3OriginalStore
    from domain_kernel.sources.infrastructure.sharepoint_reader import (
        EntraTokenProvider,
        SharePointReaderAdapter,
    )


_NOTEBOOK_EXPORTS = frozenset(
    {
        "NotebookRenderer",
        "NotebookValue",
        "disable_notebook_display",
        "enable_notebook_display",
        "render_notebook",
    }
)


_SOURCE_DESCRIPTORS = frozenset(
    {
        "CSV",
        "PDF",
        "BatchIngestionResult",
        "CopyTo",
        "Document",
        "Excel",
        "FileDescriptor",
        "FileInput",
        "IngestionFailure",
        "IngestionStage",
        "IngestionSuccess",
        "Ontology",
        "ParsedSource",
        "ReaderLocation",
        "SourceDescriptor",
        "SourceEntry",
        "SourceEntryKind",
        "SourceFolder",
        "SourceInput",
        "Statement",
        "Word",
    }
)
_SOURCE_PORTS = frozenset(
    {
        "AcquiredSource",
        "FormatParser",
        "OriginalStore",
        "ParsedChunk",
        "ParsedSourceProvider",
        "ParsedSourceResolver",
        "SourceReader",
    }
)


_SOURCE_ADAPTERS = {
    "EntraClientCredentials": "domain_kernel.sources.infrastructure.entra",
    "S3ArtifactStore": "domain_kernel.sources.infrastructure.s3_store",
    "S3OriginalStore": "domain_kernel.sources.infrastructure.s3_store",
    "AwsCredentialProvider": "domain_kernel.sources.infrastructure.aws",
    "AwsCredentialSnapshot": "domain_kernel.sources.infrastructure.aws",
    "EntraTokenProvider": "domain_kernel.sources.infrastructure.sharepoint_reader",
    "S3ReaderAdapter": "domain_kernel.sources.infrastructure.s3_reader",
    "SharePointReaderAdapter": "domain_kernel.sources.infrastructure.sharepoint_reader",
    "DoclingParser": "domain_kernel.sources.infrastructure.docling_documents",
    "DiscoveryStage": "domain_kernel.discovery.infrastructure.langgraph_gateway",
    "DiscoveryStageRoute": "domain_kernel.discovery.infrastructure.langgraph_gateway",
    "LangGraphDiscoveryGateway": "domain_kernel.discovery.infrastructure.langgraph_gateway",
    "NamedEntityHints": "domain_kernel.discovery.infrastructure.mentions",
    "LocalReplayGateway": "domain_kernel.discovery.infrastructure.local_replay",
    "LiteLLMGateway": "domain_kernel.discovery.infrastructure.litellm_gateway",
    "RapidFuzzSimilarityScorer": "domain_kernel.reconciliation.infrastructure.similarity",
}


_LAZY_ADAPTER_EXPORTS = {
    **_SOURCE_ADAPTERS,
    **dict.fromkeys(_SOURCE_DESCRIPTORS, "domain_kernel.sources.application.contracts"),
    **dict.fromkeys(_SOURCE_PORTS, "domain_kernel.sources.application.ports"),
    **dict.fromkeys(_NOTEBOOK_EXPORTS, "domain_kernel.notebook"),
}


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
    if name in _LAZY_ADAPTER_EXPORTS:
        module = import_module(name=_LAZY_ADAPTER_EXPORTS[name])
        capability: object = getattr(module, name, None)
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
    "Alignment",
    "AlignmentId",
    "AlignmentLayer",
    "AlignmentStatus",
    "AlignmentSuggestion",
    "AlignmentSuggestionId",
    "AnswerQuestion",
    "Approval",
    "ApprovalId",
    "ApproveLocalExtension",
    "Artifact",
    "ArtifactConflictError",
    "ArtifactStore",
    "ArtifactWrite",
    "AttributeAlreadyExistsError",
    "AttributeDefinition",
    "AttributeEquals",
    "AttributeId",
    "AttributeNotFoundError",
    "AttributeType",
    "AuditAction",
    "AuditId",
    "AuditOutcome",
    "AuditRecord",
    "AuditResource",
    "AuthoredContent",
    "AwsCredentialProvider",
    "AwsCredentialSnapshot",
    "BatchIngestionResult",
    "BindingWitness",
    "BlankNode",
    "BundleId",
    "BundleValidation",
    "BusinessCode",
    "BusinessDecisionDefinition",
    "Candidate",
    "CandidateId",
    "CandidatePin",
    "CardinalityBounds",
    "CardinalityRule",
    "CaseDecision",
    "CaseKind",
    "CaseStatus",
    "CellRange",
    "CellValue",
    "ChangePlanId",
    "ChangeSet",
    "CheckOutcome",
    "CheckRequirement",
    "Client",
    "ClientConfiguration",
    "ClientIntegrations",
    "CollectionKind",
    "CollectionSemanticsObligation",
    "ColumnProfile",
    "CompanyDefinitionReference",
    "ComparisonKind",
    "Compatibility",
    "CompetencyQuestion",
    "Concept",
    "ConceptDefinition",
    "ConceptReferenceType",
    "Condition",
    "ConditionId",
    "ConfigurationError",
    "ConfigurationReport",
    "ConfigurationSetting",
    "ConfigurationSource",
    "ConfirmStatement",
    "Confirmation",
    "ConfirmationMethod",
    "ConstraintDefinition",
    "ConstraintLanguage",
    "ConstraintTarget",
    "ConsumerObligation",
    "ContentHash",
    "CopyTo",
    "CorrectMapping",
    "Count",
    "CoverageStatus",
    "CoverageUnit",
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
    "Defer",
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
    "DiscoveryCoverage",
    "DiscoveryDraft",
    "DiscoveryDraftId",
    "DiscoveryFailure",
    "DiscoveryProgress",
    "DiscoveryPrompt",
    "DiscoveryResult",
    "DiscoveryRunId",
    "DiscoverySourceContext",
    "DiscoveryStage",
    "DiscoveryStageRoute",
    "DiscoveryWindow",
    "DistinctDefinitionsCheck",
    "DoclingParser",
    "Document",
    "DocumentFormat",
    "DocumentSpan",
    "DomainKernelError",
    "DomainModelBuilder",
    "DomainModelBundle",
    "EditDefinition",
    "EndpointBinding",
    "EntraClientCredentials",
    "EntraTokenProvider",
    "Event",
    "EventId",
    "EventKind",
    "Evidence",
    "EvidenceBasis",
    "EvidenceContent",
    "EvidenceId",
    "EvidenceLocator",
    "EvidenceUnavailableError",
    "Excel",
    "Exclude",
    "ExportPayload",
    "ExternalLocation",
    "ExtractionProvenance",
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
    "HeldRelationship",
    "HitPolicy",
    "IdempotencyConflictError",
    "IdentityBinding",
    "IncludeCase",
    "InferenceError",
    "InferenceInput",
    "InferredColumnType",
    "IngestedSource",
    "IngestionFailure",
    "IngestionStage",
    "IngestionSuccess",
    "InterpretationContext",
    "InvalidBundleError",
    "InvalidDecisionError",
    "InvalidOntologyError",
    "InvalidReferencePackError",
    "InvalidSchemaError",
    "Iri",
    "Issue",
    "IssueSeverity",
    "JsonSchemaProjectionRequest",
    "KeepNonblockingQuestion",
    "KeyAlreadyExistsError",
    "KeyDefinition",
    "KeyEnforcementObligation",
    "KeyId",
    "KeyNotFoundError",
    "LabelRole",
    "LabelText",
    "LangGraphDiscoveryGateway",
    "LanguageTag",
    "LinkmlProjection",
    "LinkmlProjectionRequest",
    "LinkmlSyntax",
    "LiteLLMGateway",
    "LocalReplayGateway",
    "LocalizedDescription",
    "LocalizedLabel",
    "ManualCriterion",
    "MapToDefinition",
    "MapToPlannedDefinition",
    "MapToReference",
    "MappingCorrectionAction",
    "MappingDescriptor",
    "MappingId",
    "MappingRelation",
    "MeaningText",
    "MissingCapabilityError",
    "MissingDependencyError",
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
    "ModelRequest",
    "ModelResponse",
    "ModelScope",
    "ModelSlice",
    "ModelTermReference",
    "ModelVersion",
    "ModuleExtractionMethod",
    "ModuleExtractionSupport",
    "ModuleGuarantee",
    "NamedEntityHints",
    "NotebookRenderer",
    "NotebookValue",
    "Nullability",
    "ObligationId",
    "ObligationKind",
    "Ontology",
    "OntologyAdapter",
    "OntologyCapabilities",
    "OntologyClosure",
    "OntologyClosurePin",
    "OntologyContextBinding",
    "OntologyDocument",
    "OntologyDocumentPin",
    "OntologyEntityKind",
    "OntologyImportBinding",
    "OntologyLimits",
    "OntologyModuleDefinition",
    "OntologyModuleExtractor",
    "OntologyModuleResult",
    "OntologyReasoner",
    "OntologyStatement",
    "OntologySyntax",
    "OntologyTermReference",
    "OpenValueSetAnnotation",
    "OperationInProgressError",
    "Origin",
    "OriginalCopy",
    "OriginalStore",
    "PackMaturity",
    "Page",
    "PageCursor",
    "ParsedChunk",
    "ParsedGraph",
    "ParsedOntology",
    "ParsedPart",
    "ParsedPayload",
    "ParsedSource",
    "ParsedSourceOrigin",
    "ParsedSourceProvider",
    "ParsedSourceResolver",
    "ParsedTable",
    "ParsedText",
    "Pattern",
    "PatternAdoption",
    "PatternId",
    "PatternNotFoundError",
    "Person",
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
    "ProjectionAssessment",
    "ProjectionAvailability",
    "ProjectionBlockedError",
    "ProjectionFeature",
    "ProjectionFinding",
    "ProjectionLocation",
    "ProjectionRemedy",
    "ProjectionRequest",
    "Proposal",
    "ProposalId",
    "Publication",
    "PublicationBlockedError",
    "PublicationId",
    "PublicationNotFoundError",
    "PublicationRules",
    "QuantityBinding",
    "QuantityRequiredCheck",
    "Question",
    "QuestionDisposition",
    "QuestionId",
    "RapidFuzzSimilarityScorer",
    "RdfLiteral",
    "RdfProjectionRequest",
    "RdfSyntax",
    "ReaderLocation",
    "Readiness",
    "ReadinessCheck",
    "ReasoningModelValidator",
    "ReasoningProfile",
    "ReasoningRequest",
    "ReasoningResult",
    "ReasoningSupport",
    "ReasoningTask",
    "ReferenceAlignment",
    "ReferenceAssetKind",
    "ReferenceDefinition",
    "ReferenceDefinitionId",
    "ReferenceOrigin",
    "ReferencePack",
    "ReferencePackBuild",
    "ReferencePackChange",
    "ReferencePackComposition",
    "ReferencePackDependency",
    "ReferencePackImport",
    "ReferencePackImportManifest",
    "ReferencePackNotFoundError",
    "ReferencePackObligation",
    "ReferencePackPin",
    "ReferencePackSpec",
    "ReferencePackValidation",
    "ReferenceTargetObligation",
    "Reject",
    "RelationTypeRef",
    "RelationshipBinding",
    "RelationshipCardinality",
    "RelationshipDefinition",
    "RelationshipEnforcementObligation",
    "RepresentationSupport",
    "RequirementKind",
    "ResourceLimitError",
    "RestoreDefinition",
    "RetireDefinition",
    "ReviewAction",
    "ReviewActionKind",
    "ReviewCase",
    "ReviewCaseId",
    "ReviewImpact",
    "ReviewReceipt",
    "ReviewRequirement",
    "ReviewSnapshot",
    "ReviseDefinition",
    "Role",
    "RoleId",
    "RuleDefinition",
    "RunStatus",
    "S3ArtifactStore",
    "S3OriginalStore",
    "S3ReaderAdapter",
    "ScalarDataType",
    "ScalarValueType",
    "SchemaArtifactMetadata",
    "SchemaDiscoveryOptions",
    "SchemaDocument",
    "SchemaImportResult",
    "SchemaOrigin",
    "ScopeMismatchError",
    "SemanticArtifactMetadata",
    "SemanticDocument",
    "SemanticGraphRole",
    "SemanticLinkDefinition",
    "SemanticOntologyDependency",
    "SemanticProjection",
    "SemanticRegime",
    "SemanticRelation",
    "SemanticStatus",
    "SemanticValidator",
    "ShaclModelValidator",
    "SharePointReaderAdapter",
    "SliceDefinition",
    "SnapshotReference",
    "Source",
    "SourceAlignment",
    "SourceAlignmentChange",
    "SourceAlreadyExistsError",
    "SourceDescriptor",
    "SourceDisposition",
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
    "SourceUnavailableError",
    "StaleStateError",
    "Statement",
    "StatementForm",
    "StatementIntent",
    "StatementOrigin",
    "StatementSpan",
    "StructuredValueDefinition",
    "StructuredValueType",
    "TableProfile",
    "Terminology",
    "TraversalDirection",
    "UnitAnnotation",
    "UnitBindingAnnotation",
    "UnitDefinition",
    "Unset",
    "UnsupportedBundleVersionError",
    "UnsupportedCapabilityError",
    "UnsupportedReferencePackVersionError",
    "ValidationGraphs",
    "ValidationReport",
    "ValidationReportId",
    "ValidationResponsibility",
    "ValueSetDefinition",
    "ValueSetMember",
    "ValueSetMembership",
    "ValueSetType",
    "VersionExistsError",
    "VisibleQuestion",
    "Word",
    "compose_models",
    "disable_notebook_display",
    "enable_notebook_display",
    "extract_ontology_module",
    "hello",
    "load_linkml",
    "load_ontology",
    "project_linkml",
    "project_semantics",
    "reason_ontology",
    "render_notebook",
    "serialize_ontology",
    "slice_model",
    "transcode_ontology",
    "validate_bundle",
]
