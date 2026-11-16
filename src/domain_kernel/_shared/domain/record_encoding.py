"""Canonical encoding of the SDK's closed set of persisted modeling records."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
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
from domain_kernel._shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    IncludeCase,
    ModelChangePlan,
    RestoreDefinition,
    RetireDefinition,
    ReviseDefinition,
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
)
from domain_kernel._shared.domain.ontology_assets import (
    BlankNode,
    Iri,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyTermReference,
)
from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.domain.enums.definition_change_kind import DefinitionChangeKind
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.modeling.domain.enums.definition_origin import DefinitionOrigin
from domain_kernel.modeling.domain.enums.definition_status import DefinitionStatus
from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.modeling.domain.publications import Approval, DomainModelBundle, Publication
from domain_kernel.modeling.domain.snapshots import (
    Candidate,
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
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.decisions import Accept, EditDefinition, Reject
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
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import is_non_string_sequence

if TYPE_CHECKING:
    from collections.abc import Callable

    from domain_kernel.shared.hashing import JsonValue

_RECORDS: dict[str, Callable[..., object]] = {
    record.__name__: record
    for record in (
        Approval,
        ApprovalId,
        BundleId,
        CandidatePin,
        DomainModelBundle,
        Publication,
        PublicationId,
        AcceptanceCheckDefinition,
        AcceptanceCheckResult,
        Candidate,
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
_RESTORE_FIELDS: dict[str, Callable[..., object]] = {
    # Persistence validates the original nominal IDs through the same domain invariants.
    "AttributeDefinition": AttributeDefinition._from_snapshot,  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    "KeyDefinition": KeyDefinition._from_snapshot,  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
}
_ENUMS: dict[str, type[StrEnum]] = {
    enum.__name__: enum
    for enum in (
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
        CollectionKind,
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
        ValueSetMembership,
    )
}


# Keep the canonical bytes of an ungrouped leaf and its original replay intent.
_OMIT_EMPTY_GROUP_FIELDS = {
    "ReviewCase": frozenset(
        {
            "change_plan",
            "members",
            "generated_member_case_ids",
            "grouped_by_case_id",
            "guarded_workspace_revision",
            "before_definition",
        }
    ),
    "DecisionRecord": frozenset(
        {
            "change_plan",
            "group_decision_id",
            "member_decision_ids",
            "generated_member_case_ids",
            "released_case_ids",
        }
    ),
}


def record_value(*, value: object) -> JsonValue:
    """Encode one supported authored value, retaining exact nested types."""
    tag = type(value).__name__
    if isinstance(value, StrEnum) and _ENUMS.get(tag) is type(value):
        return {"enum": tag, "value": value.value}
    if value is None or type(value) is str or type(value) is int or type(value) is bool:
        return value
    if isinstance(value, datetime):
        return {"time": value.isoformat()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, Sequence) and is_non_string_sequence(value):
        items: Sequence[object] = value
        return tuple(record_value(value=item) for item in items)
    if is_dataclass(value) and _RECORDS.get(tag) is type(value):
        attributes: dict[str, JsonValue] = {}
        for field in fields(value):
            # Reflection is limited to registered dataclass fields and checked recursively.
            item: object = getattr(value, field.name)  # pyright: ignore[reportAny]
            if field.name in _OMIT_EMPTY_GROUP_FIELDS.get(tag, ()) and item in (None, ()):
                continue
            attributes[field.name] = record_value(value=item)
        return {"record": tag, "fields": attributes}
    message = f"Cannot persist an unsupported SDK record type: {tag}"
    raise TypeError(message)


def _restore(*, value: JsonValue) -> object:
    if isinstance(value, dict):
        return _restore_object(value=value)
    if isinstance(value, Sequence) and is_non_string_sequence(value):
        return tuple(_restore(value=item) for item in value)
    return value


def _restore_object(*, value: dict[str, JsonValue]) -> object:
    if set(value) == {"enum", "value"}:
        tag, scalar = value["enum"], value["value"]
        if isinstance(tag, str) and isinstance(scalar, str) and tag in _ENUMS:
            return _ENUMS[tag](scalar)
    elif set(value) == {"time"} and isinstance(time := value["time"], str):
        return datetime.fromisoformat(time)
    elif set(value) == {"decimal"} and isinstance(decimal := value["decimal"], str):
        return Decimal(decimal)
    elif set(value) == {"record", "fields"}:
        tag, attributes = value["record"], value["fields"]
        if isinstance(tag, str) and isinstance(attributes, dict) and tag in _RECORDS:
            construct = _RESTORE_FIELDS.get(tag, _RECORDS[tag])
            return construct(**{key: _restore(value=field) for key, field in attributes.items()})
    raise ValueError("Stored data contains an invalid SDK record")


def record_bytes(*, value: object) -> bytes:
    """Encode the canonical versioned form used by durable modeling state."""
    return canonical_json_bytes(value={"version": 1, "record": record_value(value=value)})


def read_record[T](*, content: bytes, expected: type[T]) -> T:
    """Restore an exact supported record from canonical bytes."""
    # The standard JSON parser creates primitive values, arrays and string-keyed objects.
    raw: JsonValue = json.loads(content)  # pyright: ignore[reportAny]
    if not isinstance(raw, dict) or raw.get("version") != 1 or "record" not in raw:
        raise ValueError("Stored data has an unsupported modeling record version")
    loaded = _restore(value=raw["record"])
    if not isinstance(loaded, expected) or record_bytes(value=loaded) != content:
        raise ValueError("Stored data does not match its canonical SDK record")
    return loaded
