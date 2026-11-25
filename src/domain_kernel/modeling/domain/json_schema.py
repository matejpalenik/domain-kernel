"""Assess and render selected business shapes as JSON Schema 2020-12."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never
from urllib.parse import quote

from domain_kernel.modeling.domain.bundle_shapes import wire_shape
from domain_kernel.modeling.domain.interchange import (
    JSON_SCHEMA_MAPPING,
    MappingDescriptor,
    ProjectionFeature,
    ProjectionFinding,
    ProjectionLocation,
    RepresentationSupport,
    ValidationResponsibility,
)
from domain_kernel.modeling.domain.projection_analysis import blocked_feature, host_feature
from domain_kernel.modeling.domain.rdf_graphs import definition_iri, model_iri
from domain_kernel.shared.domain.acceptance import AcceptanceCheckDefinition
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
    UnitDefinition,
    ValueSetDefinition,
)
from domain_kernel.shared.domain.model_values import (
    CollectionKind,
    DataType,
    MeaningText,
    Nullability,
    ValueSetMembership,
)
from domain_kernel.shared.domain.ontology_assets import Iri
from domain_kernel.shared.domain.semantic_definitions import (
    OntologyModuleDefinition,
    SemanticLinkDefinition,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from domain_kernel.modeling.domain.interchange import ProjectionAssessment
    from domain_kernel.modeling.domain.schema_selection import PublishedShapes, SelectedDefinition
    from domain_kernel.shared.contracts import PinnedDefinitionReference
    from domain_kernel.shared.domain.data_shapes import AttributeDefinition
    from domain_kernel.shared.hashing import JsonValue

_DIALECT = "https://json-schema.org/draft/2020-12/schema"
MAPPING = MappingDescriptor(
    id=JSON_SCHEMA_MAPPING,
    vocabulary_iri=Iri(value=_DIALECT),
    supported_capabilities=(
        "object_presence",
        "array_bounds",
        "typed_envelopes",
        "unit_annotations",
    ),
    adapter_versions=(),
)


def _supported(
    *,
    location: ProjectionLocation,
    feature: ProjectionFeature,
    message: str,
    annotation: bool = False,
) -> ProjectionFinding:
    return ProjectionFinding(
        location=location,
        feature=feature,
        explanation=MeaningText(value=message),
        representation=RepresentationSupport.ANNOTATED
        if annotation
        else RepresentationSupport.NATIVE,
        validation=ValidationResponsibility.NOT_APPLICABLE
        if annotation
        else ValidationResponsibility.TARGET,
    )


def _field_findings(
    *, owner: PinnedDefinitionReference, field: AttributeDefinition
) -> Iterator[ProjectionFinding]:
    location = ProjectionLocation(definition=owner, member=field.id)
    value = field.value_type
    yield _supported(
        location=location,
        feature=ProjectionFeature.FIELD_PRESENCE,
        message="Object presence follows the field's independent required flag.",
    )
    if field.collection is not CollectionKind.SINGLE:
        yield _supported(
            location=location,
            feature=ProjectionFeature.ITEM_BOUNDS,
            message="A present array must satisfy the declared minimum and maximum.",
        )
    if field.nullability is Nullability.ALLOWED:
        yield _supported(
            location=location,
            feature=ProjectionFeature.NULLABILITY,
            message="A present single value may explicitly be null.",
        )
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
            message="Resolve and verify the exact referenced record identity and target type.",
            obligation=ReferenceTargetObligation(owner=owner, attribute=field.id),
        )
    if field.collection is CollectionKind.SET:
        yield _set_equality(owner=owner, field=field, location=location)
    for constraint in field.constraints:
        if constraint.language is not ConstraintLanguage.TEXT:
            yield blocked_feature(
                location=location,
                feature=ProjectionFeature.CONSTRAINT,
                message="Select a target that supports the authored field constraint.",
            )


def _set_equality(
    *, owner: PinnedDefinitionReference, field: AttributeDefinition, location: ProjectionLocation
) -> ProjectionFinding:
    value = field.value_type
    if isinstance(value, ValueSetType) or (
        isinstance(value, ScalarValueType)
        and value.data_type in (DataType.STRING, DataType.BOOLEAN)
    ):
        return _supported(
            location=location,
            feature=ProjectionFeature.VALUE_EQUALITY,
            message="Array uniqueness preserves exact string, code or boolean equality.",
        )
    return host_feature(
        location=location,
        feature=ProjectionFeature.VALUE_EQUALITY,
        message="Reject duplicates using typed equality before interpreting the array as a set.",
        obligation=CollectionSemanticsObligation(owner=owner, attribute=field.id),
    )


def json_findings(*, selected: Sequence[SelectedDefinition]) -> tuple[ProjectionFinding, ...]:
    """Assess the complete selected JSON shape and its supporting definitions."""
    return tuple(row for item in selected for row in _definition_findings(item=item))


def _definition_findings(*, item: SelectedDefinition) -> Iterator[ProjectionFinding]:  # noqa: C901, PLR0912
    body = item.definition.body
    owner = item.pin
    location = ProjectionLocation(definition=owner)
    if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
        yield _supported(
            location=location,
            feature=ProjectionFeature.DEFINITION,
            message="The record shape has a stable scoped definition identity.",
        )
        for field in body.attributes:
            yield from _field_findings(owner=owner, field=field)
    if isinstance(body, ConceptDefinition):
        for key in body.keys:
            yield host_feature(
                location=ProjectionLocation(definition=owner, member=key.id),
                feature=ProjectionFeature.KEY,
                message="Enforce this business key across records.",
                obligation=KeyEnforcementObligation(owner=owner, key=key.id),
            )
    if isinstance(body, StructuredValueDefinition) and body.quantity is not None:
        yield _supported(
            location=location,
            feature=ProjectionFeature.QUANTITY_BINDING,
            annotation=True,
            message="Quantity annotations preserve both fields and the optional quantity kind.",
        )
    if isinstance(body, RelationshipDefinition):
        yield host_feature(
            location=location,
            feature=ProjectionFeature.RELATIONSHIP,
            message="Verify target resolution, distinct identities and inverse participation.",
            obligation=RelationshipEnforcementObligation(relationship=owner),
        )
    if isinstance(body, UnitDefinition):
        yield _supported(
            location=location,
            feature=ProjectionFeature.UNIT_DEFINITION,
            annotation=True,
            message="Unit identity and terminology are preserved as schema metadata.",
        )
    if isinstance(body, ValueSetDefinition):
        yield _supported(
            location=location,
            feature=ProjectionFeature.KNOWN_CODES,
            message="Preserve closed code constraints or known codes for an open vocabulary.",
            annotation=body.membership is ValueSetMembership.OPEN,
        )
        for member in body.members:
            if member.unit is not None:
                yield _supported(
                    location=ProjectionLocation(definition=owner, member=member.code),
                    feature=ProjectionFeature.UNIT_REFERENCE,
                    annotation=True,
                    message="The code stays a string and retains its exact reusable-unit binding.",
                )
    if isinstance(body, (SemanticLinkDefinition, OntologyModuleDefinition)):
        yield blocked_feature(
            location=location,
            feature=ProjectionFeature.FORMAL_SEMANTICS,
            message="Use RDF or the complete bundle for the reviewed formal semantics.",
        )
    if isinstance(body, RuleDefinition):
        yield blocked_feature(
            location=location,
            feature=ProjectionFeature.CONSTRAINT,
            message="Select a mapping that supports the reviewed rule.",
        )
    if isinstance(body, AcceptanceCheckDefinition):
        yield _supported(
            location=location,
            feature=ProjectionFeature.MODEL_CHECK,
            annotation=True,
            message="Publication acceptance results remain model metadata.",
        )
    if item.definition.terminology.labels or item.definition.terminology.descriptions:
        yield _supported(
            location=location,
            feature=ProjectionFeature.TERMINOLOGY,
            annotation=True,
            message="Keep localized labels and descriptions in the manifest.",
        )


def _key(*, pin: PinnedDefinitionReference) -> str:
    return ":".join(
        quote(value, safe="-._")
        for value in (
            pin.model.scope.project_id.value,
            pin.model.scope.model_id.value,
            pin.definition_id.value,
        )
    )


def _reference(*, pin: PinnedDefinitionReference) -> str:
    return f"#/$defs/{quote(_key(pin=pin), safe=':')}"


def _identity(*, base: Iri, pin: PinnedDefinitionReference) -> dict[str, JsonValue]:
    return {
        "@id": {"type": "string", "format": "iri", "pattern": r"^[A-Za-z][A-Za-z0-9+.-]*:[^\s]+$"},
        "@type": {"const": definition_iri(base=base, identity=pin).value},
    }


def _envelope(*, base: Iri, pin: PinnedDefinitionReference) -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": _identity(base=base, pin=pin),
        "required": ["@id", "@type"],
        "additionalProperties": False,
    }


def _value_schema(
    *, index: PublishedShapes, item: SelectedDefinition, field: AttributeDefinition, base: Iri
) -> dict[str, JsonValue]:
    value = field.value_type
    match value:
        case ScalarValueType():
            return _scalar(data_type=value.data_type)
        case ConceptReferenceType():
            target = index.resolve(owner=item.pin.model, reference=value.concept)
            return _envelope(base=base, pin=target.pin)
        case StructuredValueType():
            target = index.resolve(owner=item.pin.model, reference=value.structure)
            return {"$ref": _reference(pin=target.pin)}
        case ValueSetType():
            target = index.resolve(owner=item.pin.model, reference=value.value_set)
            body = target.definition.body
            if not isinstance(body, ValueSetDefinition):
                raise TypeError("Resolve the exact published value set")
            shape: dict[str, JsonValue] = {"type": "string"}
            if body.membership is ValueSetMembership.CLOSED:
                shape["enum"] = [member.code.value for member in body.members]
            return shape
        case _:
            assert_never(value)


def _scalar(*, data_type: DataType) -> dict[str, JsonValue]:
    if data_type is DataType.DECIMAL:
        return {"type": "number"}
    if data_type in (DataType.DATE, DataType.DATETIME):
        return {"type": "string", "format": "date" if data_type is DataType.DATE else "date-time"}
    return {"type": data_type.value}


def _field_shape(
    *, index: PublishedShapes, item: SelectedDefinition, field: AttributeDefinition, base: Iri
) -> dict[str, JsonValue]:
    value = _value_schema(index=index, item=item, field=field, base=base)
    shape: dict[str, JsonValue] = {"title": field.display_name}
    if field.collection is not CollectionKind.SINGLE:
        shape["type"] = "array"
        shape["items"] = value
        shape["minItems"] = field.min_items.value if field.min_items is not None else 0
        if field.max_items is not None:
            shape["maxItems"] = field.max_items.value
        if field.collection is CollectionKind.SET:
            shape["uniqueItems"] = True
    elif field.nullability is Nullability.ALLOWED:
        shape["anyOf"] = (value, {"type": "null"})
    else:
        shape.update(value)
    return shape


def _relationship_shapes(
    *, index: PublishedShapes, item: SelectedDefinition, base: Iri
) -> Iterator[tuple[str, dict[str, JsonValue], bool]]:
    handled: set[PinnedDefinitionReference] = set()
    for selected in index.related(item=item):
        body = selected.definition.body
        if not isinstance(body, RelationshipDefinition) or selected.pin in handled:
            continue
        handled.add(selected.pin)
        owner = selected.pin.model
        source = index.resolve(owner=owner, reference=body.source_concept_id)
        target = index.resolve(owner=owner, reference=body.target_concept_id)
        if item.pin == source.pin:
            peer, bounds = target, body.cardinality.outgoing
        else:
            peer, bounds = source, body.cardinality.incoming
        value: dict[str, JsonValue] = {
            "type": "array",
            "items": _envelope(base=base, pin=peer.pin),
            "uniqueItems": True,
            "minItems": bounds.minimum.value,
        }
        if bounds.maximum is not None:
            value["maxItems"] = bounds.maximum.value
        yield f"rel:{selected.pin.definition_id.value}", value, bounds.minimum.value > 0


def _record(*, index: PublishedShapes, item: SelectedDefinition, base: Iri) -> dict[str, JsonValue]:
    definition = item.definition
    body = definition.body
    if not isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
        raise TypeError("Render a concept or structured value as a record")
    properties: dict[str, JsonValue] = {}
    required: list[str] = []
    if isinstance(body, ConceptDefinition):
        properties.update(_identity(base=base, pin=item.pin))
        required.extend(properties)
        for name, value, present in _relationship_shapes(index=index, item=item, base=base):
            properties[name] = value
            if present:
                required.append(name)
    for field in body.attributes:
        properties[field.name] = _field_shape(index=index, item=item, field=field, base=base)
        if field.required:
            required.append(field.name)
    result: dict[str, JsonValue] = {
        "type": "object",
        "title": definition.display_name,
        "description": definition.meaning,
        "properties": properties,
    }
    if required:
        result["required"] = required
    return result


def _wire(value: object) -> JsonValue:
    return wire_shape(hint=type(value)).render(value)


def _manifest_definition(*, item: SelectedDefinition) -> JsonValue:
    definition = item.definition
    return {
        "source": _wire(item.pin),
        "name": definition.name,
        "display_name": definition.display_name,
        "meaning": definition.meaning,
        "aliases": list(definition.aliases),
        "terminology": _wire(definition.terminology),
        "body": _wire(definition.body),
    }


def schema_iri(*, base: Iri, owner: PinnedDefinitionReference) -> Iri:
    """Derive the exact versioned schema document identifier."""
    prefix = model_iri(base=base, model=owner.model).value
    release = quote(owner.model.version, safe="")
    identity = quote(owner.definition_id.value, safe="")
    return Iri(value=f"{prefix}versions/{release}/schemas/{identity}")


def schema_document(
    *,
    index: PublishedShapes,
    root: SelectedDefinition,
    selected: Sequence[SelectedDefinition],
    base: Iri,
    report: ProjectionAssessment,
) -> dict[str, JsonValue]:
    """Produce a schema from the same complete selection as its assessment."""
    units, bindings = index.units(selected=selected)
    definitions: dict[str, JsonValue] = {
        _key(pin=item.pin): _record(index=index, item=item, base=base)
        for item in selected
        if isinstance(item.definition.body, (ConceptDefinition, StructuredValueDefinition))
    }
    return {
        "$schema": _DIALECT,
        "$id": schema_iri(base=base, owner=root.pin).value,
        "$ref": _reference(pin=root.pin),
        "$defs": definitions,
        "x-domain-kernel": {
            "mapping": JSON_SCHEMA_MAPPING.value,
            "model": _wire(report.model),
            "root": _wire(root.pin),
            "assessment": report.content_hash.value,
            "definitions": [_manifest_definition(item=item) for item in selected],
            "units": [_wire(item) for item in units],
            "unit_bindings": [_wire(item) for item in bindings],
            "consumer_obligations": [_wire(item) for item in report.consumer_obligations],
            "format_assertions": ["iri", "date", "date-time"],
            "parse_decimals_exactly": True,
        },
    }
