"""Canonical encoding of the SDK's closed set of persisted modeling records."""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from typing import TYPE_CHECKING, TypeGuard

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
    DiscoveryPrompt,
    DiscoveryResult,
    DiscoveryRun,
    ExtractionIntent,
    ExtractionProvenance,
    InterpretationContext,
    Proposal,
    RunStatus,
    SourceCheckpoint,
)
from domain_kernel.discovery.domain.schema_evidence import (
    SchemaMappingHint,
    SchemaObservation,
    SchemaRecordBinding,
    SchemaReviewEvidence,
)
from domain_kernel.discovery.domain.schema_options import (
    CompetencyQuestion,
    DiscoverySourceContext,
    SchemaDiscoveryOptions,
)
from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
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
    JsonSchemaProjectionRequest,
    LinkmlProjectionRequest,
    LinkmlSyntax,
    MappingDescriptor,
    ProjectionAvailability,
    ProjectionFeature,
    ProjectionFinding,
    ProjectionLocation,
    ProjectionRemedy,
    RdfProjectionRequest,
    RdfSyntax,
    RepresentationSupport,
    ValidationResponsibility,
)
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.modeling.domain.publications import Approval, Publication
from domain_kernel.modeling.domain.semantics import ReasoningRequest, ReasoningResult
from domain_kernel.modeling.domain.snapshots import (
    Candidate,
    DependencyChange,
    DomainModelBundle,
    ModelContent,
    PublicationRules,
    Readiness,
    ReadinessCheck,
    ReviewSnapshot,
    ValidationReport,
    VisibleQuestion,
)
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
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
from domain_kernel.reference_packs.domain.packs import ReferencePack
from domain_kernel.review.domain.decisions import (
    Accept,
    AnswerQuestion,
    ApproveLocalExtension,
    Confirmation,
    ConfirmationMethod,
    ConfirmStatement,
    Defer,
    EditDefinition,
    Exclude,
    KeepNonblockingQuestion,
    MapToDefinition,
    MapToReference,
    Reject,
)
from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.approval_id import ApprovalId
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import (
    CaseDecision,
    DecisionRecord,
    ReviewCase,
    ReviewReceipt,
)
from domain_kernel.review.domain.questions import (
    Question,
    QuestionDisposition,
    RequirementKind,
    ReviewRequirement,
)
from domain_kernel.shared.contracts import (
    CandidatePin,
    Count,
    Issue,
    ModelScope,
    ModelVersion,
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.codecs.decimal_text import canonical_decimal_text
from domain_kernel.shared.domain.codecs.record_restoration import construct_record
from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
from domain_kernel.shared.domain.entities.condition import Condition
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.entities.event import Event
from domain_kernel.shared.domain.entities.flow import Flow
from domain_kernel.shared.domain.entities.gateway import Gateway
from domain_kernel.shared.domain.entities.key_definition import KeyDefinition
from domain_kernel.shared.domain.entities.model_change_plan import ModelChangePlan
from domain_kernel.shared.domain.entities.role import Role
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
from domain_kernel.shared.domain.enums.reference_disposition_kind import ReferenceDispositionKind
from domain_kernel.shared.domain.enums.semantic_graph_role import SemanticGraphRole
from domain_kernel.shared.domain.enums.semantic_regime import SemanticRegime
from domain_kernel.shared.domain.enums.semantic_relation import SemanticRelation
from domain_kernel.shared.domain.enums.semantic_status import SemanticStatus
from domain_kernel.shared.domain.enums.source_disposition import SourceDisposition
from domain_kernel.shared.domain.enums.value_set_membership import ValueSetMembership
from domain_kernel.shared.domain.operations.correct_mapping import CorrectMapping
from domain_kernel.shared.domain.operations.create_definition import CreateDefinition
from domain_kernel.shared.domain.operations.include_case import IncludeCase
from domain_kernel.shared.domain.operations.map_to_planned_definition import MapToPlannedDefinition
from domain_kernel.shared.domain.operations.restore_definition import RestoreDefinition
from domain_kernel.shared.domain.operations.retire_definition import RetireDefinition
from domain_kernel.shared.domain.operations.revise_definition import ReviseDefinition
from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.domain.value_objects.acceptance_check_result import AcceptanceCheckResult
from domain_kernel.shared.domain.value_objects.attribute_equals import AttributeEquals
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
from domain_kernel.shared.domain.value_objects.definition_correspondence import (
    DefinitionCorrespondence,
)
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
from domain_kernel.shared.domain.value_objects.reference_disposition import ReferenceDisposition
from domain_kernel.shared.domain.value_objects.reference_disposition_change import (
    ReferenceDispositionChange,
)
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
from domain_kernel.shared.hashing import canonical_json_bytes
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.person_id import PersonId
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.sources.domain.coverage import CoverageStatus, CoverageUnit
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.models import (
    Evidence,
    FileOrigin,
    IngestedSource,
    OriginalCopy,
    OriginalWriteIntent,
    ProcessingRecord,
    RetainedDocument,
    RetainedExcerpt,
    Source,
    SourceProfile,
    SourceRevision,
)
from domain_kernel.sources.domain.parsed import (
    CellRange,
    DocumentSpan,
    ExternalLocation,
    ParsedGraph,
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
    StatementPayload,
)
from domain_kernel.sources.domain.tables import ColumnProfile, InferredColumnType, TableProfile

if TYPE_CHECKING:
    from collections.abc import Iterable

    from domain_kernel.shared.hashing import JsonValue

_RECORDS: dict[str, type[object]] = {
    record.__name__: record
    for record in (
        CellRange,
        DocumentSpan,
        Evidence,
        EvidenceId,
        ExternalLocation,
        OntologyStatement,
        ParsedGraph,
        ParsedPayload,
        ParsedSourceOrigin,
        ParsedTable,
        SchemaOrigin,
        ParsedText,
        RdfLiteral,
        MappingId,
        MappingDescriptor,
        ProjectionFinding,
        ProjectionLocation,
        RdfProjectionRequest,
        JsonSchemaProjectionRequest,
        LinkmlProjectionRequest,
        Artifact,
        ModelTermReference,
        OntologyModuleDefinition,
        SemanticLinkDefinition,
        CollectionSemanticsObligation,
        KeyEnforcementObligation,
        OntologyClosure,
        OntologyContextBinding,
        OntologyDocument,
        OntologyImportBinding,
        OntologyLimits,
        OntologyCapabilities,
        ModuleExtractionSupport,
        ReasoningSupport,
        ReasoningRequest,
        ReasoningResult,
        ParsedOntology,
        OntologyClosurePin,
        ReferenceTargetObligation,
        RelationshipEnforcementObligation,
        SemanticArtifactMetadata,
        SchemaArtifactMetadata,
        FileOrigin,
        IngestedSource,
        OriginalCopy,
        OriginalWriteIntent,
        ProcessingRecord,
        Person,
        PersonId,
        StatementOrigin,
        StatementPayload,
        StatementSpan,
        DiscoveryCoverage,
        CompetencyQuestion,
        DiscoverySourceContext,
        SchemaDiscoveryOptions,
        DiscoveryWindow,
        DiscoveryDraft,
        EndpointBinding,
        BindingWitness,
        HeldRelationship,
        RelationshipBinding,
        SchemaObservation,
        SchemaRecordBinding,
        SchemaReviewEvidence,
        SchemaMappingHint,
        DiscoveryFailure,
        DiscoveryResult,
        DiscoveryRun,
        SourceCheckpoint,
        Alignment,
        AlignmentId,
        AlignmentSuggestion,
        AlignmentSuggestionId,
        DiscoveryDraftId,
        DiscoveryPrompt,
        DiscoveryRunId,
        ExtractionIntent,
        ExtractionProvenance,
        InterpretationContext,
        Proposal,
        RetainedDocument,
        RetainedExcerpt,
        ColumnProfile,
        TableProfile,
        SourceProfile,
        CoverageUnit,
        AuditId,
        Source,
        SourceId,
        SourceRevision,
        SourceRevisionId,
        Activity,
        Condition,
        Event,
        Flow,
        Gateway,
        Role,
        ActivityId,
        ConditionId,
        EventId,
        FlowId,
        GatewayId,
        RoleId,
        BusinessDecisionDefinition,
        DecisionInput,
        DecisionOutput,
        DecisionRule,
        DecisionValue,
        AttributeEquals,
        CardinalityRule,
        RuleDefinition,
        ProcessDefinition,
        Pattern,
        PatternId,
        ObligationId,
        ReferenceDefinition,
        ReferenceOrigin,
        ReferencePackComposition,
        ReferencePackDependency,
        ReferencePackImportManifest,
        ReferencePackObligation,
        ReferencePackValidation,
        DefinitionBinding,
        PatternAdoption,
        MapToReference,
        ApproveLocalExtension,
        ReferenceAlignment,
        ReferencePack,
        ReferencePackChange,
        Approval,
        ApprovalId,
        BundleId,
        CandidatePin,
        Publication,
        PublicationId,
        AcceptanceCheckDefinition,
        AcceptanceCheckResult,
        Candidate,
        DomainModelBundle,
        DependencyChange,
        DependencyChangeRequest,
        DependencyRemapping,
        CandidateId,
        DistinctDefinitionsCheck,
        Issue,
        ManualCriterion,
        ModelContent,
        PublicationRules,
        QuantityRequiredCheck,
        QuestionId,
        Readiness,
        ReadinessCheck,
        ReviewSnapshot,
        ValidationReport,
        ValidationReportId,
        VisibleQuestion,
        AuthoredContent,
        CaseDecision,
        Question,
        ReviewRequirement,
        ChangePlanId,
        CreateDefinition,
        IncludeCase,
        CorrectMapping,
        MapToPlannedDefinition,
        ModelChangePlan,
        RestoreDefinition,
        RetireDefinition,
        ReviseDefinition,
        ChangeSet,
        DefinitionCorrespondence,
        ReferenceDisposition,
        ReferenceDispositionChange,
        ReferencePackPin,
        SourceAlignment,
        SourceAlignmentChange,
        ProposalId,
        DecisionRecord,
        DefinitionChange,
        ReviewReceipt,
        Accept,
        AnswerQuestion,
        Confirmation,
        Defer,
        Exclude,
        KeepNonblockingQuestion,
        MapToDefinition,
        ConfirmStatement,
        AttributeDefinition,
        AttributeId,
        BlankNode,
        BusinessCode,
        CardinalityBounds,
        ConceptDefinition,
        ConceptReferenceType,
        ConstraintDefinition,
        ContentHash,
        Count,
        DecimalFacets,
        DecimalPrecision,
        DecimalScale,
        DecisionId,
        Definition,
        DefinitionId,
        EditDefinition,
        Iri,
        KeyDefinition,
        KeyId,
        LabelText,
        LanguageTag,
        LocalizedDescription,
        LocalizedLabel,
        MeaningText,
        ModelId,
        ModelScope,
        ModelVersion,
        OntologyDocumentPin,
        OntologyTermReference,
        PinnedDefinitionReference,
        ProjectId,
        QuantityBinding,
        ReferenceDefinitionId,
        Reject,
        RelationshipCardinality,
        RelationshipDefinition,
        RelationTypeRef,
        ReviewCase,
        ReviewCaseId,
        ScalarValueType,
        StructuredValueDefinition,
        StructuredValueType,
        Terminology,
        UnitDefinition,
        ValueSetDefinition,
        ValueSetMember,
        ValueSetType,
    )
}
_ENUMS: dict[str, type[StrEnum]] = {
    enum.__name__: enum
    for enum in (
        AlignmentLayer,
        AlignmentStatus,
        RunStatus,
        ConfirmationMethod,
        QuestionDisposition,
        RequirementKind,
        LinkmlSyntax,
        EventKind,
        FlowKind,
        GatewayDirection,
        GatewayKind,
        HitPolicy,
        ObligationKind,
        PackMaturity,
        ReferenceAssetKind,
        MappingRelation,
        CheckOutcome,
        CheckRequirement,
        IssueSeverity,
        ModelKind,
        ComparisonKind,
        Compatibility,
        DefinitionChangeKind,
        SourceDisposition,
        ReferenceDispositionKind,
        CaseKind,
        CaseStatus,
        ProjectionAvailability,
        ProjectionFeature,
        ProjectionRemedy,
        RdfSyntax,
        RepresentationSupport,
        ValidationResponsibility,
        CollectionKind,
        SemanticGraphRole,
        SemanticRelation,
        ConstraintLanguage,
        ConstraintTarget,
        DataType,
        DefinitionKind,
        DefinitionOrigin,
        DefinitionStatus,
        EvidenceBasis,
        LabelRole,
        Nullability,
        OntologyEntityKind,
        ReasoningProfile,
        ModuleExtractionMethod,
        ModuleGuarantee,
        ReasoningTask,
        SemanticRegime,
        SemanticStatus,
        OntologySyntax,
        StatementForm,
        StatementIntent,
        InferredColumnType,
        CoverageStatus,
        ValueSetMembership,
    )
}


# Keep the canonical bytes of an ungrouped leaf and its original replay intent.
_OMIT_EMPTY_GROUP_FIELDS = {
    "Alignment": frozenset({"reference_shortlist_profile"}),
    "DiscoveryDraft": frozenset(
        {
            "relationship_bindings",
            "held_relationships",
            "coverage",
            "schema_observations",
            "schema_mappings",
            "schema_review_receipt",
        }
    ),
    "SchemaObservation": frozenset({"record_binding"}),
    "DiscoveryPrompt": frozenset({"schema_options"}),
    "RuleDefinition": frozenset({"cardinality"}),
    "Proposal": frozenset({"schema_review"}),
    "DiscoveryResult": frozenset({"parent_run_id"}),
    "HeldRelationship": frozenset({"dependency_ids", "relation_type"}),
    "DiscoveryRun": frozenset({"workflow_profile"}),
    "RelationshipDefinition": frozenset({"relation_type"}),
    "ProcessingRecord": frozenset({"parser_options"}),
    "OriginalWriteIntent": frozenset({"document", "excerpts"}),
    "AuthoredContent": frozenset({"schema_origins"}),
    "Definition": frozenset({"schema_origins", "evidence"}),
    "ValidationReport": frozenset({"semantic_fingerprints", "reasoning"}),
    "OntologyCapabilities": frozenset({"reasoning", "extraction"}),
    "Artifact": frozenset({"projection_limits", "semantic", "consumer_obligations", "schema"}),
    "ArtifactWrite": frozenset({"schema"}),
    "Candidate": frozenset({"dependency_bundles"}),
    "ModelChangePlan": frozenset({"pattern_adoption", "dependency_change"}),
    "ReferenceDisposition": frozenset({"definition_revision", "reference_pack", "alignment"}),
    "ReviewCase": frozenset(
        {
            "change_plan",
            "dependency_change",
            "members",
            "generated_member_case_ids",
            "grouped_by_case_id",
            "guarded_workspace_revision",
            "before_definition",
            "reference_pack",
            "reference_before",
            "run_id",
            "reconciliation_id",
            "proposal_ids",
            "evidence",
            "relationship_endpoint_definitions",
            "schema_review",
            "context_fingerprint",
            "correction_of_decision_id",
            "correction_of_case_id",
            "confirmation_subject_id",
            "question",
            "requirements",
            "reference_pack_change",
            "superseded_by_decision_id",
            "generated_by_pack_change_id",
        }
    ),
    "DecisionRecord": frozenset(
        {
            "reference_pack_change",
            "change_plan",
            "dependency_change",
            "group_decision_id",
            "member_decision_ids",
            "generated_member_case_ids",
            "released_case_ids",
        }
    ),
}


def _temporal_value(*, value: date | datetime, utc_times: bool) -> JsonValue:
    if isinstance(value, datetime):
        instant = value.astimezone(UTC) if utc_times and value.utcoffset() is not None else value
        return {"time": instant.isoformat()}
    return {"date": value.isoformat()}


def _scalar_record(*, value: date | Decimal | float, utc_times: bool) -> JsonValue:
    if isinstance(value, date):
        return _temporal_value(value=value, utc_times=utc_times)
    if isinstance(value, Decimal):
        return {"decimal": canonical_decimal_text(value=value)}
    if not isfinite(value):
        raise ValueError("Use finite stored scalars")
    return {"float": float.hex(value)}


def _is_record_sequence(value: object, /) -> TypeGuard[Sequence[object]]:
    return SequenceValidation.is_non_string_sequence(value=value)


def record_value(
    *,
    value: object,
    root_type: type[object] | None = None,
    utc_times: bool = False,
) -> JsonValue:
    """Encode one supported authored value, retaining exact nested types."""
    tag = type(value).__name__
    if isinstance(value, StrEnum) and _ENUMS.get(tag) is type(value):
        return {"enum": tag, "value": value.value}
    if value is None or type(value) is str or type(value) is int or type(value) is bool:
        return value
    if type(value) is bytes:
        return {"bytes": b64encode(value).decode("ascii")}
    if isinstance(value, (date, Decimal, float)):
        return _scalar_record(value=value, utc_times=utc_times)
    if _is_record_sequence(value):
        return tuple(record_value(value=item, utc_times=utc_times) for item in value)
    if is_dataclass(value) and (_RECORDS.get(tag) is type(value) or root_type is type(value)):
        attributes: dict[str, JsonValue] = {}
        for field in fields(value):
            # Reflection is limited to registered dataclass fields and checked recursively.
            item: object = getattr(value, field.name)  # pyright: ignore[reportAny]
            if field.name in _OMIT_EMPTY_GROUP_FIELDS.get(tag, ()) and item in (None, ()):
                continue
            attributes[field.name] = record_value(value=item, utc_times=utc_times)
        return {"record": tag, "fields": attributes}
    message = f"Cannot persist an unsupported SDK record type: {tag}"
    raise TypeError(message)


def _restore(*, value: JsonValue, root_type: type[object] | None = None) -> object:
    if isinstance(value, dict):
        return _restore_object(value=value, root_type=root_type)
    if isinstance(value, Sequence) and SequenceValidation.is_non_string_sequence(value=value):
        return tuple(_restore(value=item) for item in value)
    return value


_SCALAR_MARKERS = frozenset({"time", "date", "decimal", "float", "bytes"})


def _restore_scalar(*, value: dict[str, JsonValue]) -> object:
    if set(value) == {"bytes"} and isinstance(encoded := value["bytes"], str):
        decoded = b64decode(encoded, validate=True)
        if b64encode(decoded).decode("ascii") == encoded:
            return decoded
    if set(value) == {"time"} and isinstance(time := value["time"], str):
        return datetime.fromisoformat(time)
    if set(value) == {"date"} and isinstance(day := value["date"], str):
        return date.fromisoformat(day)
    if set(value) == {"decimal"} and isinstance(decimal := value["decimal"], str):
        return Decimal(decimal)
    if set(value) == {"float"} and isinstance(scalar := value["float"], str):
        number = float.fromhex(scalar)
        if isfinite(number) and number.hex() == scalar:
            return number
    raise ValueError("Stored data contains a malformed scalar")


def _restore_object(
    *,
    value: dict[str, JsonValue],
    root_type: type[object] | None,
) -> object:
    if set(value) == {"enum", "value"}:
        tag, scalar = value["enum"], value["value"]
        if isinstance(tag, str) and isinstance(scalar, str) and tag in _ENUMS:
            return _ENUMS[tag](scalar)
    elif _SCALAR_MARKERS.intersection(value):
        return _restore_scalar(value=value)
    elif set(value) == {"record", "fields"}:
        tag, attributes = value["record"], value["fields"]
        if isinstance(tag, str) and isinstance(attributes, dict):
            record = _RECORDS.get(tag)
            if root_type is not None and root_type.__name__ == tag:
                record = root_type
            if record is not None:
                return construct_record(
                    record=record,
                    attributes={key: _restore(value=field) for key, field in attributes.items()},
                )
    raise ValueError("Stored data contains an invalid SDK record")


def record_bytes(*, value: object, root_type: type[object] | None = None) -> bytes:
    """Encode the canonical versioned form used by durable modeling state."""
    return canonical_json_bytes(
        value={"version": 1, "record": record_value(value=value, root_type=root_type)}
    )


def _decode_json(*, content: bytes) -> JsonValue:
    # The standard JSON parser creates primitive values, arrays and string-keyed objects.
    return json.loads(content)  # pyright: ignore[reportAny]


def read_record[T](
    *,
    content: bytes,
    expected: type[T],
    root_type: type[object] | None = None,
) -> T:
    """Restore an exact supported record from canonical bytes."""
    raw = _decode_json(content=content)
    if not isinstance(raw, dict) or raw.get("version") != 1 or "record" not in raw:
        raise ValueError("Stored data has an unsupported modeling record version")
    if b'"workflow_version":"v23"' in content and _normalize_v23_options(value=raw["record"]):
        if canonical_json_bytes(value=_decode_json(content=content)) != content:
            raise ValueError("Stored data does not match its canonical SDK record")
        content = canonical_json_bytes(value=raw)
    loaded = _restore(value=raw["record"], root_type=root_type)
    if not isinstance(loaded, expected) or (
        record_bytes(value=loaded, root_type=root_type) != content
        and not _matches_discovery_pre_schema(value=loaded, raw=raw, content=content)
    ):
        raise ValueError("Stored data does not match its canonical SDK record")
    return loaded


def _normalize_v23_options(*, value: JsonValue) -> bool:
    """Remove only the retired selectors from previously captured v23 prompts."""
    if isinstance(value, list):
        return _normalize_v23_children(values=value)
    if not isinstance(value, dict):
        return False
    if value.get("record") == "SchemaDiscoveryOptions":
        fields = value.get("fields")
        if (
            isinstance(fields, dict)
            and fields.get("workflow_version") == "v23"
            and fields.get("coverage_strategy") in ("parent_only", "focused")
            and fields.get("reference_guidance") == "late_mapping"
        ):
            for key in ("workflow_version", "coverage_strategy", "reference_guidance"):
                del fields[key]
            return True
    return _normalize_v23_children(values=value.values())


def _normalize_v23_children(*, values: Iterable[JsonValue]) -> bool:
    changed = False
    for item in values:
        changed |= _normalize_v23_options(value=item)
    return changed


def _matches_discovery_pre_schema(
    *,
    value: object,
    raw: dict[str, JsonValue],
    content: bytes,
) -> bool:
    """Accept prior discovery records lacking only newly introduced default fields."""
    if isinstance(value, DiscoveryRun) and value.schema_version is None:
        optional = ("schema_version",)
    elif (
        isinstance(value, DiscoveryDraft)
        and not value.schema_modeled
        and not value.schema_questions
    ):
        optional = ("schema_questions", "schema_modeled")
    else:
        return False
    original = raw.get("record")
    if not isinstance(original, dict) or not isinstance(fields := original.get("fields"), dict):
        return False
    canonical = record_value(value=value)
    if not isinstance(canonical, dict) or not isinstance(current := canonical.get("fields"), dict):
        return False
    for key in optional:
        if key not in fields:
            _ = current.pop(key, None)
    return canonical_json_bytes(value={"version": 1, "record": canonical}) == content
