"""Render the bounded native LinkML declarations and versioned SDK annotations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never
from urllib.parse import quote

from domain_kernel.modeling.domain.bundle_shapes import wire_shape
from domain_kernel.modeling.domain.interchange import IdentityBinding
from domain_kernel.modeling.domain.linkml import OpenValueSetAnnotation
from domain_kernel.modeling.domain.rdf_graphs import definition_iri, model_iri
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.value_set_membership import ValueSetMembership
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.concept_reference_type import ConceptReferenceType
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_type import StructuredValueType
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType
from domain_kernel.shared.hashing import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.interchange import ProjectionAssessment
    from domain_kernel.modeling.domain.schema_selection import PublishedShapes, SelectedDefinition
    from domain_kernel.shared.contracts import ModelVersion, PinnedDefinitionReference
    from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
    from domain_kernel.shared.domain.value_objects.cardinality_bounds import CardinalityBounds
    from domain_kernel.shared.domain.value_objects.value_set_member import ValueSetMember
    from domain_kernel.shared.hashing import JsonValue


def wire(value: object) -> JsonValue:
    """Reuse the complete bundle's ordinary versioned value encodings."""
    return wire_shape(hint=type(value)).render(value)


def annotation(value: JsonValue) -> str:
    """Store an exact JSON value in a native LinkML annotation string."""
    return canonical_json_bytes(value=value).decode("utf-8")


def schema_iri(*, base: Iri, model: ModelVersion) -> Iri:
    """Address the selected schema's published model version."""
    prefix = model_iri(base=base, model=model).value
    return Iri(value=f"{prefix}versions/{quote(model.version, safe='')}/linkml")


@dataclass(frozen=True, kw_only=True)
class _Context:
    index: PublishedShapes
    names: dict[PinnedDefinitionReference, str]
    base: Iri

    def iri(self, *, item: SelectedDefinition) -> Iri:
        return definition_iri(base=self.base, identity=item.pin)


def _names(*, selected: Sequence[SelectedDefinition]) -> dict[PinnedDefinitionReference, str]:
    counts = Counter(item.definition.name for item in selected)
    used: set[str] = set()
    names: dict[PinnedDefinitionReference, str] = {}
    for item in selected:
        label = item.definition.name
        if counts[label] > 1:
            label = f"{label}--{item.pin.model.scope.model_id.value.encode().hex()}"
        if label in used:
            label += f"--{item.pin.definition_id.value.encode().hex()}"
        used.add(label)
        names[item.pin] = label
    return names


def _metadata(*, item: SelectedDefinition) -> dict[str, JsonValue]:
    definition = item.definition
    return {
        "dk:definition": annotation(
            {
                "version": "1",
                "name": definition.name,
                "source": wire(item.pin),
                "kind": definition.kind.value,
                "terminology": wire(definition.terminology),
            }
        )
    }


def _member_meaning(*, context: _Context, owner: ModelVersion, item: ValueSetMember) -> str | None:
    if item.unit is not None:
        return context.iri(item=context.index.resolve(owner=owner, reference=item.unit)).value
    return None if item.ontology_term is None else item.ontology_term.term_iri.value


def _vocabulary(
    *, context: _Context, item: SelectedDefinition, body: ValueSetDefinition
) -> dict[str, JsonValue]:
    meta = _metadata(item=item)
    common: dict[str, JsonValue] = {
        "title": item.definition.display_name,
        "description": item.definition.meaning,
        "aliases": list(item.definition.aliases),
        "annotations": meta,
    }
    if body.membership is ValueSetMembership.OPEN:
        common["typeof"] = "string"
        common["uri"] = context.iri(item=item).value
        meta["dk:open_value_set"] = annotation(
            wire(OpenValueSetAnnotation(source=item.pin, body=body))
        )
        return common
    common["enum_uri"] = context.iri(item=item).value
    codes: dict[str, JsonValue] = {}
    for member in body.members:
        code: dict[str, JsonValue] = {
            "title": member.label.value,
            "description": member.meaning.value,
        }
        meaning = _member_meaning(context=context, owner=item.pin.model, item=member)
        if meaning is not None:
            code["meaning"] = meaning
        codes[member.code.value] = code
    common["permissible_values"] = codes
    meta["dk:closed_value_set"] = annotation(wire(body))
    return common


def _range(*, context: _Context, item: SelectedDefinition, field: AttributeDefinition) -> str:
    value = field.value_type
    match value:
        case ScalarValueType():
            return value.data_type.value
        case (
            ConceptReferenceType(concept=target)
            | StructuredValueType(structure=target)
            | ValueSetType(value_set=target)
        ):
            return context.names[context.index.resolve(owner=item.pin.model, reference=target).pin]
        case _:
            assert_never(value)


def _local_iri(*, parent: Iri, segment: str, identifier: str) -> Iri:
    return Iri(value=f"{parent.value}/{segment}/{quote(identifier, safe='')}")


def _field(
    *, context: _Context, item: SelectedDefinition, field: AttributeDefinition
) -> tuple[dict[str, JsonValue], IdentityBinding]:
    iri = _local_iri(parent=context.iri(item=item), segment="attributes", identifier=field.id.value)
    native: dict[str, JsonValue] = {
        "title": field.display_name,
        "slot_uri": iri.value,
        "range": _range(context=context, item=item, field=field),
        "required": field.required,
        "annotations": {
            "dk:attribute": annotation(
                {
                    "version": "1",
                    "source": field.id.value,
                    "terminology": wire(field.terminology),
                }
            )
        },
    }
    if isinstance(field.value_type, (StructuredValueType, ConceptReferenceType)):
        native["inlined"] = isinstance(field.value_type, StructuredValueType)
    if field.collection is CollectionKind.SET:
        native["multivalued"] = True
        native["list_elements_unique"] = True
        native["list_elements_ordered"] = False
        native["minimum_cardinality"] = 0 if field.min_items is None else field.min_items.value
        if field.max_items is not None:
            native["maximum_cardinality"] = field.max_items.value
    return native, IdentityBinding(
        definition=item.pin, term_iri=iri, local_path=("attributes", field.id.value)
    )


def _class(
    *,
    context: _Context,
    item: SelectedDefinition,
    body: ConceptDefinition | StructuredValueDefinition,
) -> tuple[dict[str, JsonValue], tuple[IdentityBinding, ...]]:
    meta = _metadata(item=item)
    slots: dict[str, JsonValue] = {}
    identities: list[IdentityBinding] = []
    record: dict[str, JsonValue] = {
        "title": item.definition.display_name,
        "description": item.definition.meaning,
        "class_uri": context.iri(item=item).value,
        "aliases": list(item.definition.aliases),
        "annotations": meta,
        "attributes": slots,
    }
    for field in body.attributes:
        slots[field.name], binding = _field(context=context, item=item, field=field)
        identities.append(binding)
    meta["dk:field_order"] = annotation([field.name for field in body.attributes])
    if isinstance(body, ConceptDefinition) and body.keys:
        by_id = {field.id: field.name for field in body.attributes}
        keys: dict[str, JsonValue] = {}
        for key in body.keys:
            keys[key.name] = {"unique_key_slots": [by_id[field] for field in key.attributes]}
            identities.append(
                IdentityBinding(
                    definition=item.pin,
                    term_iri=_local_iri(
                        parent=context.iri(item=item), segment="keys", identifier=key.id.value
                    ),
                    local_path=("keys", key.id.value),
                )
            )
        record["unique_keys"] = keys
        meta["dk:key_labels"] = annotation(
            [{"name": key.name, "title": key.display_name} for key in body.keys]
        )
    if isinstance(body, StructuredValueDefinition) and body.quantity is not None:
        meta["dk:quantity"] = annotation(wire(body.quantity))
    return record, tuple(identities)


def _relationship_slot(  # noqa: PLR0913 - Pin both directions and their scoped identity.
    *,
    peer: str,
    inverse: str,
    iri: Iri,
    bounds: CardinalityBounds,
    definition: SelectedDefinition,
    direction: str,
) -> dict[str, JsonValue]:
    annotations = _metadata(item=definition)
    annotations["dk:direction"] = direction
    native: dict[str, JsonValue] = {
        "title": definition.definition.display_name,
        "description": definition.definition.meaning,
        "aliases": list(definition.definition.aliases),
        "slot_uri": iri.value,
        "range": peer,
        "inverse": inverse,
        "inlined": False,
        "multivalued": True,
        "list_elements_unique": True,
        "list_elements_ordered": False,
        "required": bounds.minimum.value > 0,
        "minimum_cardinality": bounds.minimum.value,
        "annotations": annotations,
    }
    if bounds.maximum is not None:
        native["maximum_cardinality"] = bounds.maximum.value
    return native


def _relationships(
    *,
    context: _Context,
    items: Sequence[SelectedDefinition],
    classes: dict[str, dict[str, JsonValue]],
) -> tuple[dict[str, JsonValue], tuple[IdentityBinding, ...]]:
    slots: dict[str, JsonValue] = {}
    identities: list[IdentityBinding] = []
    class_slots: dict[str, list[str]] = {}
    for item in items:
        body = item.definition.body
        if not isinstance(body, RelationshipDefinition):
            continue
        source = context.index.resolve(owner=item.pin.model, reference=body.source_concept_id)
        target = context.index.resolve(owner=item.pin.model, reference=body.target_concept_id)
        source_name, target_name = context.names[source.pin], context.names[target.pin]
        identity = context.iri(item=item)
        scope = item.pin.model.scope.model_id.value.encode().hex()
        name = f"dk--{scope}--{item.pin.definition_id.value.encode().hex()}"
        forward, inverse = name + "--forward", name + "--inverse"
        class_slots.setdefault(source_name, []).append(forward)
        class_slots.setdefault(target_name, []).append(inverse)
        for direction, key, other, peer, bounds in (
            ("outgoing", forward, inverse, target_name, body.cardinality.outgoing),
            ("incoming", inverse, forward, source_name, body.cardinality.incoming),
        ):
            term = _local_iri(parent=identity, segment="slots", identifier=direction)
            slots[key] = _relationship_slot(
                peer=peer,
                inverse=other,
                iri=term,
                bounds=bounds,
                definition=item,
                direction=direction,
            )
            identities.append(
                IdentityBinding(definition=item.pin, term_iri=term, local_path=(direction,))
            )
    for name, keys in class_slots.items():
        classes[name]["slots"] = keys
    return slots, tuple(identities)


def render_linkml(
    *,
    index: PublishedShapes,
    selected: Sequence[SelectedDefinition],
    excluded: Sequence[DefinitionId],
    base: Iri,
    report: ProjectionAssessment,
) -> tuple[dict[str, JsonValue], tuple[IdentityBinding, ...]]:
    """Build a closed flat schema with all members and exact provenance."""
    context = _Context(index=index, names=_names(selected=selected), base=base)
    classes: dict[str, dict[str, JsonValue]] = {}
    enums: dict[str, JsonValue] = {}
    types: dict[str, JsonValue] = {}
    identities: list[IdentityBinding] = []
    for item in selected:
        name, body = context.names[item.pin], item.definition.body
        if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
            classes[name], fields = _class(context=context, item=item, body=body)
            identities.extend(fields)
        elif isinstance(body, ValueSetDefinition):
            destination = enums if body.membership is ValueSetMembership.CLOSED else types
            destination[name] = _vocabulary(context=context, item=item, body=body)
        elif not isinstance(body, (RelationshipDefinition, UnitDefinition)):
            raise TypeError("Select only supported shape definitions")
        identities.append(IdentityBinding(definition=item.pin, term_iri=context.iri(item=item)))
    slots, directions = _relationships(context=context, items=selected, classes=classes)
    units, bindings = index.units(selected=selected)
    iri = schema_iri(base=base, model=report.model)
    class_records: dict[str, JsonValue] = dict(classes.items())
    schema: dict[str, JsonValue] = {
        "id": iri.value,
        "name": "domain-kernel-shapes",
        "title": "Published business shapes",
        "default_prefix": "dk_project",
        "prefixes": {
            "dk_project": iri.value + "/",
            "linkml": "https://w3id.org/linkml/",
            "dk": "https://domain-kernel.invalid/vocabulary/dk-linkml/1.0#",
        },
        "imports": ["linkml:types"],
        "classes": class_records,
        "slots": slots,
        "enums": enums,
        "types": types,
        "annotations": {
            "dk:units": annotation([wire(item) for item in units]),
            "dk:unit_bindings": annotation([wire(item) for item in bindings]),
            "dk:projection": annotation(
                {
                    "version": "1",
                    "base_iri": base.value,
                    "model": wire(report.model),
                    "mapping": report.mapping.id.value if report.mapping else None,
                    "assessment": report.content_hash.value,
                    "selected": [wire(item.pin) for item in selected],
                    "excluded_definition_ids": [item.value for item in excluded],
                    "dependency_models": [
                        wire(model)
                        for model in dict.fromkeys(
                            item.pin.model for item in selected if item.pin.model != report.model
                        )
                    ],
                    "obligations": [wire(item) for item in report.consumer_obligations],
                }
            ),
        },
    }
    return schema, (*identities, *directions)
