"""Closed scalar and record shapes shared by the portable encoder and its JSON Schema."""

from __future__ import annotations

import sys
from base64 import b64decode, b64encode
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from functools import cache
from types import NoneType, UnionType
from typing import (
    TYPE_CHECKING,
    Literal,
    Never,
    TypeAliasType,
    TypeIs,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)

from domain_kernel.discovery.domain.identifiers.question_id import QuestionId
from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.review.domain.decisions import ReviewAction
from domain_kernel.review.domain.identifiers.decision_id import DecisionId
from domain_kernel.review.domain.identifiers.proposal_id import ProposalId
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.contracts import (
    Count,
    DefinitionReference,
    PinnedDefinitionReference,
    SnapshotReference,
)
from domain_kernel.shared.domain.codecs.decimal_text import canonical_decimal_text
from domain_kernel.shared.domain.codecs.record_restoration import construct_record
from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
from domain_kernel.shared.domain.entities.definition import Definition
from domain_kernel.shared.domain.entities.event import Event
from domain_kernel.shared.domain.entities.flow import Flow
from domain_kernel.shared.domain.entities.gateway import Gateway
from domain_kernel.shared.domain.entities.model_change_plan import ModelChangePlan
from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.types.acceptance_predicate import AcceptancePredicate
from domain_kernel.shared.domain.types.attribute_type import AttributeType
from domain_kernel.shared.domain.types.definition_body import DefinitionBody
from domain_kernel.shared.domain.types.mapping_correction_action import MappingCorrectionAction
from domain_kernel.shared.domain.types.planned_operation import PlannedOperation
from domain_kernel.shared.domain.types.process_node import ProcessNode
from domain_kernel.shared.domain.types.process_node_id import ProcessNodeId
from domain_kernel.shared.domain.types.scalar_data_type import ScalarDataType
from domain_kernel.shared.domain.types.semantic_term import SemanticTerm
from domain_kernel.shared.domain.value_objects.change_set import ChangeSet
from domain_kernel.shared.domain.value_objects.decimal_precision import DecimalPrecision
from domain_kernel.shared.domain.value_objects.decimal_scale import DecimalScale
from domain_kernel.shared.domain.value_objects.decision_value import DecisionValue
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.domain.value_objects.reference_disposition import ReferenceDisposition
from domain_kernel.shared.domain.value_objects.source_alignment import SourceAlignment
from domain_kernel.shared.errors import DomainKernelError
from domain_kernel.shared.hashing import canonical_json_bytes
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Callable

    from domain_kernel.shared.domain.types.decision_scalar import DecisionScalar
    from domain_kernel.shared.hashing import JsonValue


class WireShapeError(ValueError):
    """A value differs from the declared closed format."""


type _Render = Callable[[object], JsonValue]
type _Parse = Callable[[JsonValue], object]


@dataclass(frozen=True, kw_only=True)
class WireShape:
    """One verified representation with its matching schema."""

    schema: JsonValue
    render: _Render
    parse: _Parse
    records: tuple[type[object], ...] = ()


@cache
def _fields(*, record: type[object]) -> dict[str, object]:
    if not is_dataclass(record):
        raise TypeError("Wire records must declare dataclass fields")
    # Type-only references resolve against this closed registry and the declaring module.
    namespace: dict[str, object] = dict(vars(sys.modules[record.__module__]))
    namespace.update(
        {
            symbol.__name__: symbol
            for symbol in (
                AcceptancePredicate,
                AttributeDefinition,
                AttributeType,
                ChangeSet,
                DecisionId,
                Definition,
                DefinitionBody,
                DefinitionId,
                DefinitionReference,
                Iri,
                MappingCorrectionAction,
                ModelChangePlan,
                OntologyDocumentPin,
                PlannedOperation,
                ProcessNode,
                ProcessNodeId,
                ProposalId,
                QuestionId,
                ReferenceDefinitionId,
                ReferenceDisposition,
                ReferencePackPin,
                ReviewAction,
                ReviewCaseId,
                ScalarDataType,
                SemanticTerm,
                SnapshotReference,
                SourceAlignment,
            )
        }
    )
    namespace.update({"Sequence": Sequence, "Never": Never, "datetime": datetime})
    hints: dict[str, object] = get_type_hints(record, globalns=namespace)
    return {field.name: hints[field.name] for field in fields(record)}


def _unrepresentable(_value: object) -> Never:
    raise WireShapeError("Value does not match its declared bundle field")


def _primitive(kind: type[object], *, schema: JsonValue) -> WireShape:
    def render(value: object) -> JsonValue:
        if kind is str and type(value) is str:
            return value
        if kind is int and type(value) is int:
            return value
        if kind is bool and type(value) is bool:
            return value
        if kind is NoneType and value is None:
            return None
        return _unrepresentable(value)

    return WireShape(schema=schema, render=render, parse=render)


def _lexical(record: type[object], *, field: str, primitive: WireShape) -> WireShape:
    def render(value: object) -> JsonValue:
        if type(value) is not record:
            return _unrepresentable(value)
        lexical: object = getattr(value, field)  # pyright: ignore[reportAny]
        return primitive.render(lexical)

    def parse(raw: JsonValue) -> object:
        return construct_record(record=record, attributes={field: primitive.parse(raw)})

    return WireShape(schema=primitive.schema, render=render, parse=parse)


def _enum(record: type[StrEnum]) -> WireShape:
    def render(value: object) -> JsonValue:
        if type(value) is not record:
            return _unrepresentable(value)
        return value.value

    def parse(raw: JsonValue) -> object:
        if type(raw) is not str:
            return _unrepresentable(raw)
        return record(raw)

    return WireShape(
        schema={"type": "string", "enum": [member.value for member in record]},
        render=render,
        parse=parse,
    )


def _constant(values: tuple[object, ...]) -> WireShape:
    def render(value: object) -> JsonValue:
        if not any(value == allowed and type(value) is type(allowed) for allowed in values):
            return _unrepresentable(value)
        if value is None or isinstance(value, StrEnum):
            return value if value is None else value.value
        if type(value) in (str, int, bool) and isinstance(value, (str, int, bool)):
            return value
        return _unrepresentable(value)

    def parse(raw: JsonValue) -> object:
        for allowed in values:
            literal = render(allowed)
            if raw == literal and type(raw) is type(literal):
                return allowed
        return _unrepresentable(raw)

    return WireShape(
        schema={"enum": [render(value) for value in values]}, render=render, parse=parse
    )


def _array(item: WireShape) -> WireShape:
    def render(value: object) -> JsonValue:
        if not isinstance(value, Sequence) or not SequenceValidation.is_non_string_sequence(
            value=value
        ):
            return _unrepresentable(value)
        items: Sequence[object] = value
        return tuple(item.render(member) for member in items)

    def parse(raw: JsonValue) -> object:
        if not isinstance(raw, Sequence) or not SequenceValidation.is_non_string_sequence(
            value=raw
        ):
            return _unrepresentable(raw)
        return tuple(item.parse(member) for member in raw)

    return WireShape(
        schema={"type": "array", "items": item.schema},
        render=render,
        parse=parse,
        records=item.records,
    )


def _choice(variants: tuple[WireShape, ...]) -> WireShape:
    def render(value: object) -> JsonValue:
        for variant in variants:
            try:
                return variant.render(value)
            except WireShapeError:
                continue
        return _unrepresentable(value)

    def parse(raw: JsonValue) -> object:
        for variant in variants:
            try:
                return variant.parse(raw)
            except (ValueError, TypeError, DomainKernelError):
                continue
        return _unrepresentable(raw)

    return WireShape(
        schema={"oneOf": [item.schema for item in variants]},
        render=render,
        parse=parse,
        records=tuple(record for item in variants for record in item.records),
    )


def _utc_text(value: object) -> str:
    if type(value) is not datetime or value.utcoffset() is None:
        return _unrepresentable(value)
    return value.astimezone(UTC).isoformat(timespec="microseconds").removesuffix("+00:00") + "Z"


def _decimal_text(value: object) -> str:
    if type(value) is not Decimal or not value.is_finite():
        return _unrepresentable(value)
    return canonical_decimal_text(value=value)


def _base64_text(value: object) -> str:
    if type(value) is not bytes:
        return _unrepresentable(value)
    return b64encode(value).decode("ascii")


def _base64_bytes(value: str) -> bytes:
    return b64decode(value, validate=True)


def _date_text(value: object) -> str:
    if type(value) is not date:
        return _unrepresentable(value)
    return value.isoformat()


def _string_parse(
    *,
    render: Callable[[object], str],
    convert: Callable[[str], object],
    schema: JsonValue,
) -> WireShape:
    def parse(raw: JsonValue) -> object:
        if type(raw) is not str:
            return _unrepresentable(raw)
        restored = convert(raw)
        if raw != render(restored):
            return _unrepresentable(raw)
        return restored

    return WireShape(schema=schema, render=render, parse=parse)


def _tagged_reference(record: type[ReferenceDefinitionId]) -> WireShape:
    def render(value: object) -> JsonValue:
        if type(value) is not record:
            return _unrepresentable(value)
        return {"kind": "reference_definition", "id": value.value}

    def parse(raw: JsonValue) -> object:
        if not isinstance(raw, dict) or set(raw) != {"kind", "id"}:
            return _unrepresentable(raw)
        identifier = raw["id"]
        if raw["kind"] != "reference_definition" or type(identifier) is not str:
            return _unrepresentable(raw)
        return record(value=identifier)

    return WireShape(
        schema={
            "type": "object",
            "properties": {
                "kind": {"const": "reference_definition"},
                "id": {"type": "string", "minLength": 1},
            },
            "required": ["kind", "id"],
            "additionalProperties": False,
        },
        render=render,
        parse=parse,
    )


def _flow_nodes_shape() -> WireShape:
    def render(value: object) -> JsonValue:
        if isinstance(value, (ActivityId, EventId, GatewayId)):
            return value.value
        return _unrepresentable(value)

    return WireShape(
        schema={"type": "string", "minLength": 1},
        render=render,
        parse=_unrepresentable,
    )


def _is_record_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return isinstance(value, tuple)


def _process_node_index(*, attributes: dict[str, object]) -> dict[str, ProcessNodeId]:
    nodes: dict[str, ProcessNodeId] = {}
    for field in ("activities", "events", "gateways"):
        group = attributes[field]
        if not _is_record_tuple(group):
            raise WireShapeError("Process nodes require known collections")
        members: tuple[object, ...] = group
        for member in members:
            if not isinstance(member, (Activity, Event, Gateway)) or member.id.value in nodes:
                raise WireShapeError("Use one declared process node per ID")
            nodes[member.id.value] = member.id
    return nodes


def _flow_from_wire(*, raw: JsonValue, nodes: dict[str, ProcessNodeId]) -> Flow:
    members = _members(record=Flow)
    if not isinstance(raw, dict) or raw.keys() != members.keys():
        raise WireShapeError("Use the declared flow format")
    attributes: dict[str, object] = {}
    for field, member in members.items():
        value = raw[field]
        if field in ("source_id", "target_id"):
            if type(value) is not str or value not in nodes:
                raise WireShapeError("Use the ID of a node declared by this process")
            attributes[field] = nodes[value]
        else:
            attributes[field] = member.parse(value)
    return Flow.restore(**attributes)


def _process_from_wire(*, raw: dict[str, JsonValue], members: dict[str, WireShape]) -> object:
    attributes = {
        name: member.parse(raw[name]) for name, member in members.items() if name != "flows"
    }
    nodes = _process_node_index(attributes=attributes)
    flows = raw["flows"]
    if not isinstance(flows, Sequence) or not SequenceValidation.is_non_string_sequence(
        value=flows
    ):
        raise WireShapeError("Use a flow array")
    attributes["flows"] = tuple(_flow_from_wire(raw=item, nodes=nodes) for item in flows)
    return construct_record(record=ProcessDefinition, attributes=attributes)


def _optional_fields(*, record: type[object]) -> frozenset[str]:
    return (
        frozenset(
            field.name for field in fields(record) if field.metadata.get("wire_omit_empty") is True
        )
        if is_dataclass(record)
        else frozenset()
    )


def _record_shape(*, record: type[object]) -> WireShape:
    optional = _optional_fields(record=record)

    def render(value: object) -> JsonValue:
        if type(value) is not record:
            return _unrepresentable(value)
        result: dict[str, JsonValue] = {}
        for name, member in _members(record=record).items():
            field: object = getattr(value, name)  # pyright: ignore[reportAny]
            if name not in optional or field not in (None, ()):
                result[name] = member.render(field)
        return result

    def parse(raw: JsonValue) -> object:
        members = _members(record=record)
        if (
            not isinstance(raw, dict)
            or raw.keys() - members.keys()
            or members.keys() - raw.keys() - optional
        ):
            return _unrepresentable(raw)
        if record is ProcessDefinition:
            return _process_from_wire(raw=raw, members=members)
        return construct_record(
            record=record,
            attributes={
                name: member.parse(raw[name]) for name, member in members.items() if name in raw
            },
        )

    return WireShape(
        schema={"$ref": f"#/$defs/{record.__name__}"},
        render=render,
        parse=parse,
        records=(record,),
    )


@cache
def _members(*, record: type[object]) -> dict[str, WireShape]:
    return {name: wire_shape(hint=hint) for name, hint in _fields(record=record).items()}


@cache
def _dataclass_shape(*, record: type[object]) -> WireShape:
    names = tuple(_fields(record=record))
    if names != ("value",):
        return _record_shape(record=record)
    primitive = wire_shape(hint=_fields(record=record)["value"])
    if record is ContentHash:
        primitive = _primitive(str, schema={"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"})
    elif record is Count or record is DecimalScale:
        primitive = _primitive(int, schema={"type": "integer", "minimum": 0})
    elif record is DecimalPrecision:
        primitive = _primitive(int, schema={"type": "integer", "minimum": 1})
    elif issubclass(record, OpaqueIdentifier):
        primitive = _primitive(str, schema={"type": "string", "minLength": 1})
    return _lexical(record, field="value", primitive=primitive)


_PRIMITIVES: dict[object, WireShape] = {
    str: _primitive(str, schema={"type": "string"}),
    int: _primitive(int, schema={"type": "integer"}),
    bool: _primitive(bool, schema={"type": "boolean"}),
    NoneType: _primitive(NoneType, schema={"type": "null"}),
    bytes: _string_parse(
        render=_base64_text,
        convert=_base64_bytes,
        schema={"type": "string", "contentEncoding": "base64"},
    ),
    datetime: _string_parse(
        render=_utc_text,
        convert=datetime.fromisoformat,
        schema={
            "type": "string",
            "format": "date-time",
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$",
        },
    ),
    date: _string_parse(
        render=_date_text,
        convert=date.fromisoformat,
        schema={"type": "string", "format": "date"},
    ),
    Decimal: _string_parse(
        render=_decimal_text,
        convert=Decimal,
        schema={"type": "string", "pattern": r"^-?(0|[1-9]\d*)(\.\d*[1-9])?$"},
    ),
}


def _boolean_literal(text: str) -> bool:
    if text not in ("true", "false"):
        raise WireShapeError("Use a canonical boolean literal")
    return text == "true"


_SCALAR_CONVERTERS: dict[DataType, Callable[[str], DecisionScalar]] = {
    DataType.STRING: str,
    DataType.INTEGER: int,
    DataType.BOOLEAN: _boolean_literal,
    DataType.DECIMAL: Decimal,
    DataType.DATE: date.fromisoformat,
    DataType.DATETIME: datetime.fromisoformat,
}


def _decision_scalar(*, kind: DataType, text: str) -> DecisionScalar:
    converter = _SCALAR_CONVERTERS.get(kind)
    if converter is None:
        raise WireShapeError("Use a supported scalar decision literal")
    return converter(text)


def _decision_value_shape() -> WireShape:
    def render(value: object) -> JsonValue:
        if type(value) is not DecisionValue:
            return _unrepresentable(value)
        raw = _PRIMITIVES[type(value.value)].render(value.value)
        lexical = str(raw).lower() if type(raw) is bool else str(raw)
        return {"data_type": value.data_type.value, "lexical_value": lexical}

    def parse(raw: JsonValue) -> object:
        if not isinstance(raw, dict) or set(raw) != {"data_type", "lexical_value"}:
            return _unrepresentable(raw)
        kind, text = raw["data_type"], raw["lexical_value"]
        if type(kind) is not str or type(text) is not str:
            return _unrepresentable(raw)
        value = DecisionValue(value=_decision_scalar(kind=DataType(kind), text=text))
        if render(value) != raw:
            return _unrepresentable(raw)
        return value

    shapes: dict[DataType, JsonValue] = {
        DataType.STRING: {"type": "string"},
        DataType.BOOLEAN: {"enum": ["false", "true"]},
        DataType.INTEGER: {"type": "string", "pattern": r"^(0|-?[1-9]\d*)$"},
        DataType.DECIMAL: _PRIMITIVES[Decimal].schema,
        DataType.DATE: _PRIMITIVES[date].schema,
        DataType.DATETIME: _PRIMITIVES[datetime].schema,
    }
    return WireShape(
        schema={
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"data_type": {"const": kind.value}, "lexical_value": schema},
                    "required": ["data_type", "lexical_value"],
                    "additionalProperties": False,
                }
                for kind, schema in shapes.items()
            ]
        },
        render=render,
        parse=parse,
    )


@cache
def wire_shape(*, hint: object) -> WireShape:
    """Resolve one closed field type shared by the encoder, decoder and schema."""
    if hint is ProcessNodeId or hint is DefinitionReference:
        return _reference_wire_shape(hint=hint)
    if isinstance(hint, (TypeAliasType, TypeVar)):
        return wire_shape(hint=_expand_alias(hint=hint))
    origin: object = get_origin(hint)
    args: tuple[object, ...] = get_args(hint)
    if origin is tuple or origin is Sequence:
        return _sequence_shape(origin=origin, members=args)
    if origin is Literal:
        return _constant(args)
    if origin is UnionType:
        return _choice(tuple(wire_shape(hint=item) for item in _flatten(choices=args)))
    return _named_shape(hint=hint)


def _reference_wire_shape(*, hint: object) -> WireShape:
    if hint is ProcessNodeId:
        return _flow_nodes_shape()
    return _choice(
        (
            wire_shape(hint=DefinitionId),
            wire_shape(hint=PinnedDefinitionReference),
            _tagged_reference(ReferenceDefinitionId),
        )
    )


def _sequence_shape(*, origin: object, members: tuple[object, ...]) -> WireShape:
    if origin is tuple and not members:
        return _constant_array()
    if origin is tuple and members[1:] != (Ellipsis,):
        return _fixed_tuple(items=tuple(wire_shape(hint=member) for member in members))
    return _array(wire_shape(hint=members[0]))


def _named_shape(*, hint: object) -> WireShape:
    if hint is Never:
        return WireShape(schema=False, render=_unrepresentable, parse=_unrepresentable)
    if (primitive := _PRIMITIVES.get(hint)) is not None:
        return primitive
    if hint is DecisionValue:
        return _decision_value_shape()
    if isinstance(hint, type) and issubclass(hint, StrEnum):
        return _enum(hint)
    if isinstance(hint, type) and is_dataclass(hint):
        return _dataclass_shape(record=hint)
    raise TypeError("Use a registered bundle wire field type")


def _expand_alias(*, hint: object) -> object:
    if isinstance(hint, TypeVar):
        default: object = hint.__default__  # pyright: ignore[reportAny] - Stdlib TypeVar reflection.
        return default
    if not isinstance(hint, TypeAliasType):
        return hint
    expanded: object = hint.__value__  # pyright: ignore[reportAny] - Stdlib alias reflection.
    return expanded


def _flatten(*, choices: tuple[object, ...]) -> tuple[object, ...]:
    resolved: list[object] = []
    for choice in choices:
        hint = choice if choice is DefinitionReference else _expand_alias(hint=choice)
        origin: object = get_origin(hint)
        args: tuple[object, ...] = get_args(hint)
        resolved.extend(_flatten(choices=args) if origin is UnionType else (hint,))
    return tuple(resolved)


def _fixed_tuple(*, items: tuple[WireShape, ...]) -> WireShape:
    def render(value: object) -> JsonValue:
        if not _is_record_tuple(value) or len(value) != len(items):
            return _unrepresentable(value)
        members: tuple[object, ...] = value
        return tuple(shape.render(part) for shape, part in zip(items, members, strict=True))

    def parse(raw: JsonValue) -> object:
        if (
            not isinstance(raw, Sequence)
            or not SequenceValidation.is_non_string_sequence(value=raw)
            or len(raw) != len(items)
        ):
            return _unrepresentable(raw)
        return tuple(shape.parse(part) for shape, part in zip(items, raw, strict=True))

    return WireShape(
        schema={
            "type": "array",
            "prefixItems": [shape.schema for shape in items],
            "minItems": len(items),
            "maxItems": len(items),
        },
        render=render,
        parse=parse,
        records=tuple(record for shape in items for record in shape.records),
    )


def _constant_array() -> WireShape:
    def render(value: object) -> JsonValue:
        if (
            isinstance(value, Sequence)
            and SequenceValidation.is_non_string_sequence(value=value)
            and len(value) == 0
        ):
            return ()
        return _unrepresentable(value)

    return WireShape(
        schema={"type": "array", "maxItems": 0},
        render=render,
        parse=render,
    )


def bundle_schema(*, root: type[object]) -> dict[str, JsonValue]:
    """Build the closed schema for exactly the record graph reachable from the root."""
    schemas: dict[str, JsonValue] = {}
    pending = [root]
    while pending:
        record = pending.pop()
        name = record.__name__
        if name in schemas:
            continue
        members = _members(record=record)
        schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {field: shape.schema for field, shape in members.items()},
            "required": tuple(
                name for name in members if name not in _optional_fields(record=record)
            ),
            "additionalProperties": False,
        }
        if record is AttributeDefinition:
            schema["allOf"] = [
                {
                    "if": {"properties": {"collection": {"const": "single"}}},
                    "then": {
                        "properties": {
                            "min_items": {"type": "null"},
                            "max_items": {"type": "null"},
                        }
                    },
                    "else": {
                        "properties": {
                            "min_items": {"type": "integer", "minimum": 0},
                            "nullability": {"const": "forbidden"},
                        }
                    },
                }
            ]
        schemas[name] = schema
        for member in members.values():
            pending.extend(member.records)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{root.__name__}",
        "$defs": schemas,
    }


def parse_wire_record[T](*, document: dict[str, JsonValue], record: type[T]) -> T:
    """Restore the exact root type and require its field representation to be canonical."""
    shape = wire_shape(hint=record)
    value = shape.parse(document)
    if not isinstance(value, record) or type(value) is not record:
        raise WireShapeError("Supply the declared root record")
    if canonical_json_bytes(value=shape.render(value)) != canonical_json_bytes(value=document):
        raise WireShapeError("Use the declared scalar and field representations")
    return value
