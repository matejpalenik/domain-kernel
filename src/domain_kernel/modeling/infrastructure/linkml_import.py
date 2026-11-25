"""Reconstruct fresh, reviewable business shapes from exact native LinkML schemas."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.interchange import (
    UnitAnnotation,
    UnitBindingAnnotation,
    require_projection_base,
)
from domain_kernel.modeling.domain.linkml import OpenValueSetAnnotation, SchemaImportResult
from domain_kernel.modeling.domain.rdf_graphs import definition_iri
from domain_kernel.modeling.infrastructure.linkml_closure import (
    Entry,
    expanded,
    items,
    record,
    text,
)
from domain_kernel.modeling.infrastructure.linkml_import_values import (
    annotation_value,
    bound,
    flag,
    keys,
    metadata,
    new_definition_id,
    origin,
    sdk_annotations,
    wire_annotation,
    wire_object,
)
from domain_kernel.review.domain.identifiers.change_plan_id import ChangePlanId
from domain_kernel.shared.contracts import Count, Issue, PinnedDefinitionReference
from domain_kernel.shared.domain.authoring import (
    AuthoredContent,
    CreateDefinition,
    ModelChangePlan,
)
from domain_kernel.shared.domain.data_shapes import (
    AttributeDefinition,
    ConceptReferenceType,
    KeyDefinition,
    QuantityBinding,
    ScalarValueType,
    StructuredValueType,
    ValueSetType,
)
from domain_kernel.shared.domain.definitions import (
    ConceptDefinition,
    RelationshipDefinition,
    StructuredValueDefinition,
    ValueSetDefinition,
    ValueSetMember,
)
from domain_kernel.shared.domain.model_values import (
    BusinessCode,
    CardinalityBounds,
    CollectionKind,
    DataType,
    LabelText,
    MeaningText,
    RelationshipCardinality,
    Terminology,
    ValueSetMembership,
)
from domain_kernel.shared.domain.naming import resolve_names
from domain_kernel.shared.domain.ontology_assets import Iri
from domain_kernel.shared.domain.shape_graph import validate_body_graph

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.interchange import MappingDescriptor
    from domain_kernel.modeling.domain.models import ModelInfo
    from domain_kernel.modeling.infrastructure.linkml_closure import Fragment, SchemaClosure
    from domain_kernel.modeling.infrastructure.linkml_import_values import DefinitionMetadata
    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.data_shapes import AttributeType
    from domain_kernel.shared.domain.definitions import DefinitionBody
    from domain_kernel.shared.domain.model_values import ScalarDataType
    from domain_kernel.shared.domain.schema_origins import SchemaOrigin
    from domain_kernel.shared.hashing import JsonValue

_SCALAR: dict[str, ScalarDataType] = {
    "string": DataType.STRING,
    "integer": DataType.INTEGER,
    "decimal": DataType.DECIMAL,
    "boolean": DataType.BOOLEAN,
    "date": DataType.DATE,
    "datetime": DataType.DATETIME,
}
_ZERO = Count(value=0)
_COMMON = {"title", "description", "aliases", "annotations"}
_CLASS = _COMMON | {"class_uri", "attributes", "slots", "unique_keys"}
_SLOT = _COMMON | {
    "slot_uri",
    "range",
    "required",
    "multivalued",
    "list_elements_unique",
    "list_elements_ordered",
    "minimum_cardinality",
    "maximum_cardinality",
    "inlined",
    "inlined_as_list",
    "inverse",
}
_SCHEMA = _COMMON | {
    "id",
    "name",
    "default_prefix",
    "default_range",
    "prefixes",
    "imports",
    "classes",
    "slots",
    "types",
    "enums",
    "license",
    "version",
}
_COMPOSITION = {"dk:units", "dk:unit_bindings", "dk:projection"}


@dataclass(frozen=True, kw_only=True)
class _Declared:
    entry: Entry
    metadata: DefinitionMetadata
    annotations: dict[str, JsonValue]
    identifier: DefinitionId


@dataclass(frozen=True, kw_only=True)
class _Unit:
    annotation: UnitAnnotation
    iri: Iri
    identifier: DefinitionId
    origins: tuple[SchemaOrigin, ...]


def _fragment_base(*, config: dict[str, JsonValue]) -> Iri | None:
    projection = config.get("dk:projection")
    if projection is None:
        return None
    entries = record(value=annotation_value(native=projection))
    keys(
        raw=entries,
        supported={
            "version",
            "base_iri",
            "model",
            "mapping",
            "assessment",
            "selected",
            "excluded_definition_ids",
            "dependency_models",
            "obligations",
        },
    )
    if entries.get("version") != "1":
        raise ValueError("Use a supported projection annotation")
    base = Iri(value=text(value=entries.get("base_iri")))
    require_projection_base(value=base)
    return base


def _list_annotation[T](*, native: JsonValue, kind: type[T]) -> tuple[T, ...]:
    if native is None:
        return ()
    return tuple(
        wire_object(value=item, kind=kind) for item in items(value=annotation_value(native=native))
    )


def _units(
    *, closure: SchemaClosure
) -> tuple[
    dict[PinnedDefinitionReference, _Unit],
    dict[tuple[PinnedDefinitionReference, BusinessCode], UnitBindingAnnotation],
]:
    definitions: dict[PinnedDefinitionReference, _Unit] = {}
    edges: dict[tuple[PinnedDefinitionReference, BusinessCode], UnitBindingAnnotation] = {}
    for fragment in closure.fragments:
        keys(raw=fragment.raw, supported=_SCHEMA)
        config = sdk_annotations(raw=fragment.raw, fragment=fragment, allowed=_COMPOSITION)
        base = _fragment_base(config=config)
        for offset, unit in enumerate(
            _list_annotation(native=config.get("dk:units"), kind=UnitAnnotation)
        ):
            if base is None:
                raise ValueError("Supply the scoped projection base for reusable units")
            iri = definition_iri(base=base, identity=unit.source)
            source = origin(
                fragment=fragment,
                dependencies=closure.dependencies,
                iri=iri,
                path=("annotations", "dk:units", offset),
            )
            previous = definitions.get(unit.source)
            if previous is None:
                definitions[unit.source] = _Unit(
                    annotation=unit,
                    iri=iri,
                    identifier=new_definition_id(),
                    origins=(source,),
                )
            elif previous.annotation != unit or previous.iri != iri:
                raise ValueError("Supply consistent annotations for each reusable unit")
            else:
                definitions[unit.source] = replace(previous, origins=(*previous.origins, source))
        for link in _list_annotation(
            native=config.get("dk:unit_bindings"), kind=UnitBindingAnnotation
        ):
            key = link.source, link.code
            if edges.setdefault(key, link) != link:
                raise ValueError("Supply a single consistent unit binding for each code")
    return definitions, edges


def _member_unit(
    *,
    member: ValueSetMember,
    source: PinnedDefinitionReference | None,
    units: dict[PinnedDefinitionReference, _Unit],
    edges: dict[tuple[PinnedDefinitionReference, BusinessCode], UnitBindingAnnotation],
) -> tuple[ValueSetMember, str | None]:
    link = None if source is None else edges.get((source, member.code))
    if member.unit is None:
        if link is not None:
            raise ValueError("Match every unit binding to its authored code")
        term = member.ontology_term
        return member, None if term is None else term.term_iri.value
    if source is None or link is None or link.unit not in units:
        raise ValueError("Supply the exact reusable unit and its bound code")
    if isinstance(member.unit, PinnedDefinitionReference):
        matched = member.unit == link.unit
    else:
        matched = link.unit.model == source.model and link.unit.definition_id == member.unit
    if not matched:
        raise ValueError("Match the source and revision of the bound unit")
    selected = units[link.unit]
    return replace(member, unit=selected.identifier), selected.iri.value


def _code(
    *,
    name: str,
    native: JsonValue,
    member: ValueSetMember | None = None,
    expected_iri: str | None = None,
    fragment: Fragment,
) -> ValueSetMember:
    detail = record(value=native)
    keys(raw=detail, supported={"title", "description", "meaning", "text"})
    if "text" in detail and detail["text"] != name:
        raise ValueError("Use the exact permissible-value code")
    if "meaning" in detail:
        native_iri = expanded(raw=detail["meaning"], prefixes=fragment.prefixes).value
        if member is not None and native_iri != expected_iri:
            raise ValueError(
                "Match the native permissible meaning to the exact unit or original term"
            )
    elif expected_iri is not None:
        raise ValueError("Retain the declared code meaning IRI")
    label = LabelText(value=text(value=detail.get("title", name)))
    description = MeaningText(value=text(value=detail.get("description")))
    if member is None:
        return ValueSetMember(code=BusinessCode(value=name), label=label, meaning=description)
    if member.label != label or member.meaning != description:
        raise ValueError("Resolve conflicts between native and annotated code labels or meanings")
    return member


@dataclass(frozen=True, kw_only=True)
class _Collection:
    required: bool
    form: CollectionKind
    minimum: Count | None
    maximum: Count | None


def _collection(*, raw: dict[str, JsonValue]) -> _Collection:
    required = flag(raw=raw, name="required")
    multiple = flag(raw=raw, name="multivalued")
    minimum = bound(raw=raw, name="minimum_cardinality")
    maximum = bound(raw=raw, name="maximum_cardinality")
    if multiple:
        if not flag(raw=raw, name="list_elements_unique") or flag(
            raw=raw, name="list_elements_ordered"
        ):
            raise ValueError("Specify unordered multivalued fields with distinct items")
        return _Collection(
            required=required, form=CollectionKind.SET, minimum=minimum or _ZERO, maximum=maximum
        )
    if (
        minimum is not None
        or maximum is not None
        or "list_elements_unique" in raw
        or "list_elements_ordered" in raw
    ):
        raise ValueError("Omit item bounds and collection options for single-valued fields")
    return _Collection(required=required, form=CollectionKind.SINGLE, minimum=None, maximum=None)


def _pieces(*, entry: Entry) -> tuple[tuple[str, JsonValue], ...]:
    return tuple(record(value=entry.raw.get("attributes", {})).items())


@final
class _Import:
    """Hold one detached schema snapshot and allocate each proposed identity once."""

    def __init__(self, *, closure: SchemaClosure, reason: str) -> None:
        self.closure = closure
        self.reason = reason
        self.units, self.edges = _units(closure=closure)
        self.declared: dict[str, _Declared] = {}
        self.types: dict[str, ScalarDataType] = dict(_SCALAR)
        self.groups: dict[str, str] = {}
        self.range_names = {
            entry.iri: name
            for (group, name), entry in closure.entries.items()
            if group != "slots" and entry.iri is not None
        }
        self.structured: set[str] = set()
        self.slots: dict[str, Entry] = {}
        self.owners: dict[str, list[str]] = defaultdict(list)
        self.operation_list: list[CreateDefinition] = []
        self.consumed_edges: set[tuple[PinnedDefinitionReference, BusinessCode]] = set()
        self._register()

    def _register(self) -> None:
        by_pin: dict[PinnedDefinitionReference, _Declared] = {}
        for (group, name), entry in self.closure.entries.items():
            if group == "slots":
                keys(raw=entry.raw, supported=_SLOT)
                self.slots[name] = entry
                continue
            if name in self.groups or name in _SCALAR:
                raise ValueError("Use distinct native class, type and enumeration names")
            self.groups[name] = group
            if group == "types" and self._register_type(entry=entry):
                continue
            allowed = (
                {"dk:quantity", "dk:field_order", "dk:key_labels"}
                if group == "classes"
                else {"dk:closed_value_set"}
                if group == "enums"
                else {"dk:open_value_set"}
            )
            meta, values = metadata(entry=entry, allowed=allowed)
            identifier = new_definition_id()
            if meta.pin is not None and meta.pin in by_pin:
                original = by_pin[meta.pin]
                if group != "types" or (original.metadata, original.annotations) != (meta, values):
                    raise ValueError("Supply consistent declarations for each annotated source")
                identifier = original.identifier
            declared = _Declared(
                entry=entry, metadata=meta, annotations=values, identifier=identifier
            )
            self.declared[name] = declared
            if meta.pin is not None:
                by_pin[meta.pin] = declared
            if group == "classes":
                keys(raw=entry.raw, supported=_CLASS)
                self._class_declaration(name=name, declared=declared)
            if group == "enums":
                keys(raw=entry.raw, supported=_COMMON | {"enum_uri", "permissible_values"})
        self._infer_embedded_classes()

    def _register_type(self, *, entry: Entry) -> bool:
        keys(raw=entry.raw, supported=_COMMON | {"typeof", "type_uri", "uri"})
        values = sdk_annotations(
            raw=entry.raw,
            fragment=entry.fragments[0],
            allowed={"dk:definition", "dk:open_value_set"},
        )
        target = text(value=entry.raw.get("typeof"))
        if target not in _SCALAR:
            raise ValueError("Select a direct alias of a supported primitive type")
        if "dk:open_value_set" not in values:
            if "dk:definition" in values:
                meta, _ = metadata(entry=entry, allowed=set())
                if meta.kind != "value_set":
                    raise ValueError("Use type annotations only for declared open vocabularies")
            self.types[entry.name] = _SCALAR[target]
            return True
        if target != "string":
            raise ValueError("Open vocabularies require an unrestricted string range")
        return False

    def _class_declaration(self, *, name: str, declared: _Declared) -> None:
        qualifier = declared.metadata.kind
        if qualifier not in (None, "concept", "structured_value"):
            raise ValueError("Declare a concept or structured value for a native class")
        if qualifier == "structured_value":
            self.structured.add(name)
        for native in items(value=declared.entry.raw.get("slots", ())):
            key = text(value=native)
            if name in self.owners[key]:
                raise ValueError("List each class slot once")
            self.owners[key].append(name)

    def _infer_embedded_classes(self) -> None:
        if self.owners.keys() - self.slots.keys():
            raise ValueError("Supply every named class slot")
        if self.slots.keys() - self.owners.keys():
            raise ValueError("Attach each selected named slot to an owning class")
        for name, declaration in self.declared.items():
            if self.groups[name] != "classes":
                continue
            for _, value, fragment in self._slots_for(entry=declaration.entry):
                slot = record(value=value)
                if flag(raw=slot, name="inlined"):
                    target = self._range_name(raw=slot.get("range"), fragment=fragment)
                    if self.groups.get(target) != "classes":
                        raise ValueError("Use inlining only for a declared structured class")
                    if self.declared[target].metadata.kind == "concept":
                        raise ValueError("Use identity references for declared concepts")
                    self.structured.add(target)

    def _slots_for(self, *, entry: Entry) -> tuple[tuple[str, JsonValue, Fragment], ...]:
        fields: list[tuple[str, JsonValue, Fragment]] = [
            (name, spec, entry.fragments[0]) for name, spec in _pieces(entry=entry)
        ]
        for native in items(value=entry.raw.get("slots", ())):
            key = text(value=native)
            slot = self.slots[key]
            if "inverse" not in slot.raw:
                fields.append((key, slot.raw, slot.fragments[0]))
        return tuple(fields)

    def _value_type(self, *, spec: dict[str, JsonValue], fragment: Fragment) -> AttributeType:
        native = spec["range"] if "range" in spec else fragment.raw.get("default_range", "string")
        name = self._range_name(raw=native, fragment=fragment)
        inlined = flag(raw=spec, name="inlined")
        if flag(raw=spec, name="inlined_as_list") and not inlined:
            raise ValueError("Use list embedding only for structured values")
        if name in self.types:
            if inlined:
                raise ValueError("Use scalar values without class embedding")
            return ScalarValueType(data_type=self.types[name])
        selected = self.declared.get(name)
        if selected is None:
            raise ValueError("Resolve every supported slot range by its declaration")
        if self.groups[name] == "classes":
            if inlined != (name in self.structured):
                raise ValueError("Distinguish embedded structured values from concept references")
            if inlined:
                return StructuredValueType(structure=selected.identifier)
            return ConceptReferenceType(concept=selected.identifier)
        if inlined:
            raise ValueError("Use value-set codes as plain strings")
        return ValueSetType(value_set=selected.identifier)

    def _range_name(self, *, raw: JsonValue, fragment: Fragment) -> str:
        name = text(value=raw)
        if name in self.groups or name in self.types or ":" not in name:
            return name
        return self.range_names[expanded(raw=name, prefixes=fragment.prefixes)]

    def _field(
        self,
        *,
        name: str,
        spec: dict[str, JsonValue],
        fragment: Fragment,
    ) -> tuple[AttributeDefinition, AttributeId | None]:
        keys(raw=spec, supported=_SLOT)
        if "inverse" in spec:
            raise ValueError("Declare inverse relationships through named class slots")
        values = sdk_annotations(raw=spec, fragment=fragment, allowed={"dk:attribute"})
        annotation = values.get("dk:attribute")
        terms = Terminology()
        source = None
        if annotation is not None:
            fields = record(value=annotation_value(native=annotation))
            keys(raw=fields, supported={"version", "source", "terminology"})
            if fields.get("version") != "1":
                raise ValueError("Use a supported attribute annotation version")
            source = AttributeId(value=text(value=fields.get("source")))
            terms = wire_object(value=fields.get("terminology"), kind=Terminology)
        lookup, _ = resolve_names(name=None, display_name=name)
        collection = _collection(raw=spec)
        return AttributeDefinition(
            name=lookup,
            display_name=text(value=spec.get("title", name)),
            value_type=self._value_type(spec=spec, fragment=fragment),
            required=collection.required,
            collection=collection.form,
            min_items=collection.minimum,
            max_items=collection.maximum,
            terminology=terms,
        ), source

    def _record_fields(
        self, *, native: Entry
    ) -> tuple[dict[str, AttributeDefinition], dict[AttributeId, AttributeId]]:
        fields: dict[str, AttributeDefinition] = {}
        attribute_ids: dict[AttributeId, AttributeId] = {}
        for name, raw, fragment in self._slots_for(entry=native):
            if name in fields:
                raise ValueError("Declare each local field exactly once")
            field, original_id = self._field(name=name, spec=record(value=raw), fragment=fragment)
            fields[name] = field
            if original_id is not None:
                if original_id in attribute_ids:
                    raise ValueError("Use distinct attribute source identities")
                attribute_ids[original_id] = field.id
        return fields, attribute_ids

    def _record_body(self, *, declared: _Declared) -> ConceptDefinition | StructuredValueDefinition:
        native = declared.entry
        fields, attribute_ids = self._record_fields(native=native)
        ordered = _ordered_fields(
            fields=fields, annotation=declared.annotations.get("dk:field_order")
        )
        quantity = declared.annotations.get("dk:quantity")
        if native.name in self.structured:
            if native.raw.get("unique_keys") or "dk:key_labels" in declared.annotations:
                raise ValueError("Only concepts carry business keys")
            binding = (
                None if quantity is None else wire_annotation(native=quantity, kind=QuantityBinding)
            )
            if binding is not None:
                binding = replace(
                    binding,
                    magnitude=attribute_ids[binding.magnitude],
                    unit=attribute_ids[binding.unit],
                )
            return StructuredValueDefinition(attributes=ordered, quantity=binding)
        if quantity is not None:
            raise ValueError("Quantity annotations belong to structured values")
        return ConceptDefinition(
            attributes=ordered,
            keys=_keys(
                entry=native, fields=fields, annotation=declared.annotations.get("dk:key_labels")
            ),
        )

    def _vocabulary_body(self, *, declared: _Declared, group: str) -> ValueSetDefinition:
        entry = declared.entry
        source = declared.metadata.pin
        native_codes: dict[str, JsonValue] = {}
        if group == "types":
            annotation = wire_annotation(
                native=declared.annotations.get("dk:open_value_set"), kind=OpenValueSetAnnotation
            )
            if source != annotation.source or declared.metadata.kind != "value_set":
                raise ValueError("Match the open vocabulary to its exact source identity")
            body = annotation.body
        else:
            native_codes = record(value=entry.raw.get("permissible_values"))
            raw = declared.annotations.get("dk:closed_value_set")
            if raw is None:
                return ValueSetDefinition(
                    membership=ValueSetMembership.CLOSED,
                    members=[
                        _code(name=name, native=value, fragment=entry.fragments[0])
                        for name, value in native_codes.items()
                    ],
                )
            body = wire_annotation(native=raw, kind=ValueSetDefinition)
            if (
                source is None
                or declared.metadata.kind != "value_set"
                or body.membership is not ValueSetMembership.CLOSED
            ):
                raise ValueError(
                    "Match a closed vocabulary annotation to its exact enumeration identity"
                )
            if native_codes.keys() != {item.code.value for item in body.members}:
                raise ValueError("Keep native and annotated closed vocabulary codes identical")
        members: list[ValueSetMember] = []
        for member in body.members:
            imported, native_iri = _member_unit(
                member=member, source=source, units=self.units, edges=self.edges
            )
            if source is not None and member.unit is not None:
                self.consumed_edges.add((source, member.code))
            if group == "enums":
                imported = _code(
                    name=member.code.value,
                    native=native_codes[member.code.value],
                    member=imported,
                    expected_iri=native_iri,
                    fragment=entry.fragments[0],
                )
            members.append(imported)
        return replace(body, members=tuple(members))

    def _origin(self, *, entry: Entry, group: str) -> tuple[SchemaOrigin, ...]:
        return tuple(
            origin(
                fragment=fragment,
                dependencies=self.closure.dependencies,
                iri=entry.iri,
                path=(group, entry.name),
            )
            for fragment in entry.fragments
        )

    def _add(
        self,
        *,
        declared: _Declared,
        body: DefinitionBody,
        origins: Sequence[SchemaOrigin],
    ) -> None:
        info = declared.metadata
        content = AuthoredContent(
            name=info.name,
            display_name=info.title,
            meaning=info.description,
            body=body,
            aliases=info.aliases,
            terminology=info.terminology,
            schema_origins=origins,
        )
        self.operation_list.append(
            CreateDefinition(
                definition_id=declared.identifier,
                content=content,
                reason=self.reason,
            )
        )

    def _pair(self, *, first: Entry, second: Entry) -> None:
        src, dst = self.owners[first.name], self.owners[second.name]
        if (
            len(src) != 1
            or len(dst) != 1
            or src[0] in self.structured
            or dst[0] in self.structured
            or self._range_name(raw=first.raw.get("range"), fragment=first.fragments[0]) != dst[0]
            or self._range_name(raw=second.raw.get("range"), fragment=second.fragments[0]) != src[0]
        ):
            raise ValueError("Pair inverse slots between exact opposing owning concepts")
        left, left_values = metadata(entry=first, allowed={"dk:direction"})
        right, right_values = metadata(entry=second, allowed={"dk:direction"})
        orientation = left_values.get("dk:direction"), right_values.get("dk:direction")
        if orientation == ("incoming", "outgoing"):
            self._pair(first=second, second=first)
            return
        if orientation not in ((None, None), ("outgoing", "incoming")):
            raise ValueError("Use consistent inverse relationship direction annotations")
        if (left.pin is not None or right.pin is not None) and (
            left != right or left.kind != "relationship" or orientation == (None, None)
        ):
            raise ValueError("Bind both directions to one consistent reviewed relationship")
        relation = RelationshipDefinition(
            source_concept_id=self.declared[src[0]].identifier,
            target_concept_id=self.declared[dst[0]].identifier,
            cardinality=RelationshipCardinality(
                outgoing=_participation(entry=first), incoming=_participation(entry=second)
            ),
        )
        self._add(
            declared=_Declared(
                entry=first, metadata=left, annotations=left_values, identifier=new_definition_id()
            ),
            body=relation,
            origins=(
                *self._origin(entry=first, group="slots"),
                *self._origin(entry=second, group="slots"),
            ),
        )

    def operations(self) -> tuple[CreateDefinition, ...]:
        """Translate each checked declaration and preserve all exact source origins."""
        for captured in self.units.values():
            unit = captured.annotation
            content = AuthoredContent(
                name=unit.name,
                display_name=unit.display_name,
                meaning=unit.meaning,
                body=unit.body,
                aliases=unit.aliases,
                terminology=unit.terminology,
                schema_origins=captured.origins,
            )
            self.operation_list.append(
                CreateDefinition(
                    definition_id=captured.identifier,
                    content=content,
                    reason=self.reason,
                )
            )
        for name, declared in self.declared.items():
            group = self.groups[name]
            body = (
                self._record_body(declared=declared)
                if group == "classes"
                else self._vocabulary_body(declared=declared, group=group)
            )
            self._add(
                declared=declared,
                body=body,
                origins=self._origin(entry=declared.entry, group=group),
            )
        done: set[str] = set()
        for name, first in sorted(self.slots.items()):
            native = first.raw.get("inverse")
            if native is None or name in done:
                continue
            other = text(value=native)
            second = self.slots.get(other)
            if second is None or other == name or second.raw.get("inverse") != name:
                raise ValueError("Provide both mutually declared inverse slots")
            self._pair(first=first, second=second)
            done.update((name, other))
        if self.consumed_edges != self.edges.keys():
            raise ValueError("Remove unbound or unknown unit binding annotations")
        return _unique_proposals(proposals=self.operation_list)


def _ordered_fields(
    *, fields: dict[str, AttributeDefinition], annotation: JsonValue
) -> tuple[AttributeDefinition, ...]:
    if annotation is None:
        return tuple(fields.values())
    names = tuple(text(value=item) for item in items(value=annotation_value(native=annotation)))
    if len(names) != len(fields) or set(names) != fields.keys():
        raise ValueError("Match the annotated field order to the native declarations")
    return tuple(fields[name] for name in names)


def _keys(
    *, entry: Entry, fields: dict[str, AttributeDefinition], annotation: JsonValue
) -> tuple[KeyDefinition, ...]:
    native = record(value=entry.raw.get("unique_keys", {}))
    labels: dict[str, str] = {}
    if annotation is not None:
        for value in items(value=annotation_value(native=annotation)):
            row = record(value=value)
            keys(raw=row, supported={"name", "title"})
            name = text(value=row.get("name"))
            if name in labels:
                raise ValueError("Declare each key label once")
            labels[name] = text(value=row.get("title"))
        if labels.keys() != native.keys():
            raise ValueError("Match key labels to the native business keys")
    result: list[KeyDefinition] = []
    for name in labels or native:
        spec = record(value=native[name])
        keys(raw=spec, supported={"unique_key_slots"})
        identifiers = [
            fields[text(value=value)].id for value in items(value=spec.get("unique_key_slots"))
        ]
        lookup, _ = resolve_names(name=None, display_name=name)
        result.append(
            KeyDefinition(name=lookup, display_name=labels.get(name, name), attributes=identifiers)
        )
    return tuple(result)


def _participation(*, entry: Entry) -> CardinalityBounds:
    spec = _collection(raw=entry.raw)
    if (
        spec.form is not CollectionKind.SET
        or spec.minimum is None
        or "minimum_cardinality" not in entry.raw
        or flag(raw=entry.raw, name="inlined")
        or spec.required != (spec.minimum.value > 0)
    ):
        raise ValueError("Specify explicit compatible directional participation bounds")
    return CardinalityBounds(minimum=spec.minimum, maximum=spec.maximum)


def _unique_proposals(*, proposals: Sequence[CreateDefinition]) -> tuple[CreateDefinition, ...]:
    identities: dict[DefinitionId, CreateDefinition] = {}
    names: set[str] = set()
    for proposal in proposals:
        existing = identities.get(proposal.definition_id)
        if existing is not None:
            combined = tuple(
                dict.fromkeys((*existing.content.schema_origins, *proposal.content.schema_origins))
            )
            if replace(existing.content, schema_origins=()) != replace(
                proposal.content, schema_origins=()
            ):
                raise ValueError("Resolve inconsistent aliases of the same source definition")
            identities[proposal.definition_id] = replace(
                existing, content=replace(existing.content, schema_origins=combined)
            )
        else:
            name = proposal.content.name
            if name in names:
                raise ValueError("Choose distinct local lookup names before requesting an import")
            names.add(name)
            identities[proposal.definition_id] = proposal
    return tuple(identities.values())


def import_shapes(
    *,
    closure: SchemaClosure,
    model_info: ModelInfo,
    reason: str,
    mapping: MappingDescriptor,
) -> SchemaImportResult:
    """Build a fresh plan with no access to the receiving workspace."""
    try:
        proposals = _Import(closure=closure, reason=reason).operations()
        bodies: dict[DefinitionReference, DefinitionBody] = {
            item.definition_id: item.content.body for item in proposals
        }
        issues = validate_body_graph(bodies=bodies)
    except (KeyError, ValueError, TypeError, RecursionError):
        return SchemaImportResult(
            plan=None,
            mapping=mapping,
            origins=(),
            issues=(
                Issue(
                    code="unsupported_linkml_shape",
                    path=("schema",),
                    message="Check the supported declarations, bounds and SDK annotations.",
                ),
            ),
        )
    if not proposals:
        issues = (
            Issue(
                code="empty_linkml_schema",
                path=("schema",),
                message="Supply at least one supported shape declaration.",
            ),
        )
    origins = tuple(origin for proposal in proposals for origin in proposal.content.schema_origins)
    plan = (
        None
        if issues
        else ModelChangePlan(
            id=ChangePlanId(value=uuid4().hex),
            scope=model_info.scope,
            expected_workspace_revision=model_info.revision,
            reason=reason,
            bindings=(),
            operations=proposals,
        )
    )
    return SchemaImportResult(plan=plan, mapping=mapping, origins=origins, issues=issues)
