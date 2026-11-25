"""Assess every selected shape before RDF rendering or artifact selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.interchange import (
    ProjectionFeature,
    ProjectionFinding,
    ProjectionLocation,
    RepresentationSupport,
    ValidationResponsibility,
)
from domain_kernel.modeling.domain.projection_analysis import blocked_feature, host_feature
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.domain.artifacts import (
    CollectionSemanticsObligation,
    KeyEnforcementObligation,
    ReferenceTargetObligation,
    RelationshipEnforcementObligation,
)
from domain_kernel.shared.domain.business_decisions import RuleDefinition
from domain_kernel.shared.domain.data_shapes import (
    ConceptReferenceType,
    ConstraintLanguage,
    ScalarValueType,
    StructuredValueType,
    ValueSetType,
)
from domain_kernel.shared.domain.definitions import (
    ConceptDefinition,
    RelationshipDefinition,
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.model_values import (
    CollectionKind,
    DataType,
    MeaningText,
    Nullability,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.shared.domain.data_shapes import AttributeDefinition


def _support(
    *,
    location: ProjectionLocation,
    feature: ProjectionFeature,
    message: str,
    annotated: bool = False,
) -> ProjectionFinding:
    return ProjectionFinding(
        location=location,
        feature=feature,
        representation=RepresentationSupport.ANNOTATED
        if annotated
        else RepresentationSupport.NATIVE,
        validation=ValidationResponsibility.NOT_APPLICABLE
        if annotated
        else ValidationResponsibility.TARGET,
        explanation=MeaningText(value=message),
    )


def _collection(
    *,
    owner: PinnedDefinitionReference,
    field: AttributeDefinition,
    location: ProjectionLocation,
) -> Iterator[ProjectionFinding]:
    if field.collection is CollectionKind.LIST:
        yield blocked_feature(
            location=location,
            feature=ProjectionFeature.COLLECTION_KIND,
            message="Use the complete bundle to preserve order and repeated list values.",
        )
        return
    if field.collection is CollectionKind.SINGLE:
        yield _support(
            location=location,
            feature=ProjectionFeature.FIELD_PRESENCE,
            message="A single value has maximum one. Its minimum depends on requiredness.",
        )
        return
    assert field.min_items is not None  # noqa: S101 - A validated collection stores a minimum.
    if field.required != (field.min_items.value > 0):
        yield blocked_feature(
            location=location,
            feature=ProjectionFeature.FIELD_PRESENCE,
            message=(
                "Use optional sets with zero minimum or required sets with positive minimum "
                "for direct RDF predicates."
            ),
        )
        yield blocked_feature(
            location=location,
            feature=ProjectionFeature.ITEM_BOUNDS,
            message="One value count cannot encode this combination of presence and bounds.",
        )
    else:
        yield _support(
            location=location,
            feature=ProjectionFeature.FIELD_PRESENCE,
            message="The requiredness agrees with this RDF set's nonempty representation.",
        )
        yield _support(
            location=location,
            feature=ProjectionFeature.ITEM_BOUNDS,
            message="SHACL enforces this set's explicit value counts.",
        )
    kind = field.value_type
    if isinstance(kind, StructuredValueType):
        yield blocked_feature(
            location=location,
            feature=ProjectionFeature.VALUE_EQUALITY,
            message="Use the complete bundle to preserve structured set equality.",
        )
    elif isinstance(kind, ValueSetType) or (
        isinstance(kind, ScalarValueType) and kind.data_type is DataType.STRING
    ):
        yield _support(
            location=location,
            feature=ProjectionFeature.VALUE_EQUALITY,
            message="RDF's distinct lexical string values preserve this set's equality.",
        )
    else:
        yield host_feature(
            location=location,
            feature=ProjectionFeature.VALUE_EQUALITY,
            message="Enforce canonical value equality before constructing the RDF set.",
            obligation=CollectionSemanticsObligation(owner=owner, attribute=field.id),
        )


def _fields(
    *,
    owner: PinnedDefinitionReference,
    fields: Sequence[AttributeDefinition],
) -> Iterator[ProjectionFinding]:
    for field in fields:
        location = ProjectionLocation(definition=owner, member=field.id)
        yield from _collection(owner=owner, field=field, location=location)
        if field.nullability is Nullability.ALLOWED:
            yield blocked_feature(
                location=location,
                feature=ProjectionFeature.NULLABILITY,
                message="Use the complete bundle to preserve a distinct present null value.",
            )
        value = field.value_type
        if isinstance(value, ScalarValueType) and value.decimal is not None:
            yield blocked_feature(
                location=location,
                feature=ProjectionFeature.DECIMAL_FACETS,
                message="Use the complete bundle for exact decimal precision and scale.",
            )
        if isinstance(value, ConceptReferenceType):
            yield host_feature(
                location=location,
                feature=ProjectionFeature.REFERENCE_TARGET,
                message="Verify the referenced record in the consuming application.",
                obligation=ReferenceTargetObligation(owner=owner, attribute=field.id),
            )


def rdf_findings(*, bundles: Sequence[DomainModelBundle]) -> tuple[ProjectionFinding, ...]:
    """Analyze the full root and dependency shape closure in deterministic order."""
    result: list[ProjectionFinding] = []
    for bundle in bundles:
        for definition in sorted(bundle.content.definitions, key=lambda item: item.id.value):
            owner = PinnedDefinitionReference(
                model=bundle.model_version,
                definition_id=definition.id,
                definition_revision=definition.revision,
            )
            body = definition.body
            if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
                result.extend(_fields(owner=owner, fields=body.attributes))
            if isinstance(body, ConceptDefinition):
                result.extend(
                    host_feature(
                        location=ProjectionLocation(definition=owner, member=key.id),
                        feature=ProjectionFeature.KEY,
                        message="Enforce the declared key across input records.",
                        obligation=KeyEnforcementObligation(owner=owner, key=key.id),
                    )
                    for key in body.keys
                )
            if isinstance(body, RelationshipDefinition):
                result.append(
                    host_feature(
                        location=ProjectionLocation(definition=owner),
                        feature=ProjectionFeature.RELATIONSHIP,
                        message="Enforce relationship identity and reference integrity.",
                        obligation=RelationshipEnforcementObligation(relationship=owner),
                    )
                )
            if isinstance(body, RuleDefinition):
                for constraint in body.constraints:
                    report = (
                        _support(
                            location=ProjectionLocation(definition=owner),
                            feature=ProjectionFeature.CONSTRAINT,
                            message="Carry the reviewed constraint in its declared role.",
                            annotated=True,
                        )
                        if constraint.language
                        in (ConstraintLanguage.TEXT, ConstraintLanguage.SHACL)
                        else blocked_feature(
                            location=ProjectionLocation(definition=owner),
                            feature=ProjectionFeature.CONSTRAINT,
                            message="Select a supported mapping or retain the complete bundle.",
                        )
                    )
                    result.append(report)
    return tuple(result)
