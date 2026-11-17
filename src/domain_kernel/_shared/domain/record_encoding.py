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
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.acceptance import (
    AcceptanceCheckDefinition,
    AcceptanceCheckResult,
    CheckOutcome,
    CheckRequirement,
    DistinctDefinitionsCheck,
    ManualCriterion,
    QuantityRequiredCheck,
)
from domain_kernel._shared.domain.artifacts import (
    CollectionSemanticsObligation,
    KeyEnforcementObligation,
    ReferenceTargetObligation,
    RelationshipEnforcementObligation,
    SemanticArtifactMetadata,
    SemanticGraphRole,
)
from domain_kernel._shared.domain.audit import Artifact
from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    IncludeCase,
    ModelChangePlan,
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
    DefinitionCorrespondence,
    ReferenceDisposition,
    ReferenceDispositionChange,
    ReferenceDispositionKind,
    SourceAlignment,
    SourceAlignmentChange,
    SourceDisposition,
)
from domain_kernel._shared.domain.data_shapes import (
    AttributeDefinition,
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
    ConceptDefinition,
    Definition,
    EvidenceBasis,
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
    Terminology,
    ValueSetMembership,
    canonical_decimal_text,
)
from domain_kernel._shared.domain.ontology_assets import (
    BlankNode,
    Iri,
    OntologyClosurePin,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologySyntax,
    OntologyTermReference,
)
from domain_kernel._shared.domain.ontology_closure import (
    OntologyClosure,
    OntologyContextBinding,
    OntologyImportBinding,
)
from domain_kernel._shared.domain.ontology_documents import (
    OntologyDocument,
    OntologyLimits,
    ParsedOntology,
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
    Role,
)
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel._shared.domain.rdf import OntologyStatement, RdfLiteral
from domain_kernel._shared.domain.record_restoration import construct_record
from domain_kernel._shared.domain.semantic_definitions import (
    ModelTermReference,
    OntologyModuleDefinition,
    SemanticLinkDefinition,
    SemanticRelation,
)
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
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
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId
from domain_kernel.reference_packs.api.packs import ReferencePack
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
from domain_kernel.shared.contracts import (
    CandidatePin,
    Count,
    Issue,
    ModelScope,
    ModelVersion,
    PinnedDefinitionReference,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.hashing import canonical_json_bytes
from domain_kernel.shared.identifiers.audit_id import AuditId
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import is_non_string_sequence
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
)

if TYPE_CHECKING:
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
        ParsedText,
        RdfLiteral,
        MappingId,
        MappingDescriptor,
        ProjectionFinding,
        ProjectionLocation,
        RdfProjectionRequest,
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
        ParsedOntology,
        OntologyClosurePin,
        ReferenceTargetObligation,
        RelationshipEnforcementObligation,
        SemanticArtifactMetadata,
        FileOrigin,
        IngestedSource,
        OriginalCopy,
        OriginalWriteIntent,
        ProcessingRecord,
        SourceProfile,
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
        ChangePlanId,
        CreateDefinition,
        IncludeCase,
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
        OntologySyntax,
        ValueSetMembership,
    )
}


# Keep the canonical bytes of an ungrouped leaf and its original replay intent.
_OMIT_EMPTY_GROUP_FIELDS = {
    "ValidationReport": frozenset({"semantic_fingerprints"}),
    "Artifact": frozenset({"projection_limits", "semantic", "consumer_obligations"}),
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
        }
    ),
    "DecisionRecord": frozenset(
        {
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
    if isinstance(value, Sequence) and is_non_string_sequence(value):
        items: Sequence[object] = value
        return tuple(record_value(value=item, utc_times=utc_times) for item in items)
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
    if isinstance(value, Sequence) and is_non_string_sequence(value):
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


def read_record[T](
    *,
    content: bytes,
    expected: type[T],
    root_type: type[object] | None = None,
) -> T:
    """Restore an exact supported record from canonical bytes."""
    # The standard JSON parser creates primitive values, arrays and string-keyed objects.
    raw: JsonValue = json.loads(content)  # pyright: ignore[reportAny]
    if not isinstance(raw, dict) or raw.get("version") != 1 or "record" not in raw:
        raise ValueError("Stored data has an unsupported modeling record version")
    loaded = _restore(value=raw["record"], root_type=root_type)
    if (
        not isinstance(loaded, expected)
        or record_bytes(value=loaded, root_type=root_type) != content
    ):
        raise ValueError("Stored data does not match its canonical SDK record")
    return loaded
