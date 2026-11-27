"""Strict reading of native LinkML values and the registered SDK annotations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel.modeling.domain.bundle_shapes import parse_wire_record
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.interchange import LINKML_MAPPING
from domain_kernel.modeling.domain.portable_json import read_portable_object
from domain_kernel.modeling.infrastructure.linkml_closure import items, record, text
from domain_kernel.modeling.infrastructure.linkml_documents import VOCABULARY
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.domain.value_objects.count import Count
from domain_kernel.shared.domain.value_objects.pinned_definition_reference import (
    PinnedDefinitionReference,
)
from domain_kernel.shared.domain.value_objects.schema_origin import SchemaOrigin
from domain_kernel.shared.domain.value_objects.terminology import Terminology

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.linkml import SchemaDocument
    from domain_kernel.modeling.infrastructure.linkml_closure import Entry, Fragment
    from domain_kernel.shared.domain.value_objects.iri import Iri
    from domain_kernel.shared.json_value import JsonValue


def keys(*, raw: dict[str, JsonValue], supported: set[str]) -> None:
    """Reject every undeclared native field or annotation key."""
    if raw.keys() - supported:
        raise ValueError("Use only the declared bounded LinkML fields")


def sdk_annotations(
    *,
    raw: dict[str, JsonValue],
    fragment: Fragment,
    allowed: set[str],
) -> dict[str, JsonValue]:
    """Read only annotations that belong to the registered SDK dialect."""
    values = record(value=raw.get("annotations", {}))
    keys(raw=values, supported=allowed)
    if values and fragment.prefixes.get("dk") != VOCABULARY.value:
        raise ValueError("Use the registered Domain Kernel annotation namespace")
    return values


def annotation_value(*, native: JsonValue) -> JsonValue:
    """Decode a bounded exact JSON annotation carried in a LinkML value."""
    if isinstance(native, dict):
        keys(raw=native, supported={"value"})
        native = native.get("value")
    return read_portable_object(
        payload='{"value":' + text(value=native) + "}",
        expected_hash=None,
        max_bytes=4 * 1024 * 1024,
        max_depth=40,
        resource="LinkML annotation",
    )["value"]


def wire_annotation[T](*, native: JsonValue, kind: type[T]) -> T:
    """Decode a reusable closed wire record from a native annotation."""
    return parse_wire_record(document=record(value=annotation_value(native=native)), record=kind)


def wire_object[T](*, value: JsonValue, kind: type[T]) -> T:
    """Decode one declared wire record inside a larger annotation."""
    return parse_wire_record(document=record(value=value), record=kind)


def flag(*, raw: dict[str, JsonValue], name: str, default: bool = False) -> bool:
    """Read a native flag without converting a numeric or textual value."""
    value = raw.get(name, default)
    if type(value) is not bool:
        raise TypeError("Use an explicit boolean flag")
    return value


def bound(*, raw: dict[str, JsonValue], name: str, default: Count | None = None) -> Count | None:
    """Read a cardinality precisely without deriving presence from size."""
    if name not in raw:
        return default
    value = raw[name]
    if type(value) is not int:
        raise TypeError("Use an exact integer cardinality")
    return Count(value=value)


def new_definition_id() -> DefinitionId:
    """Mint a receiving-workspace identity independently of source metadata."""
    return DefinitionId(value=uuid4().hex)


@dataclass(frozen=True, kw_only=True)
class DefinitionMetadata:
    """Native labels and exact versioned annotations used by the importer."""

    name: str
    title: str
    description: str
    aliases: tuple[str, ...]
    terminology: Terminology
    pin: PinnedDefinitionReference | None
    kind: str | None


def metadata(*, entry: Entry, allowed: set[str]) -> tuple[DefinitionMetadata, dict[str, JsonValue]]:
    """Use native display values with exact source metadata for lookup identity."""
    raw = entry.raw
    entries = sdk_annotations(
        raw=raw, fragment=entry.fragments[0], allowed={"dk:definition", *allowed}
    )
    origin = entries.get("dk:definition")
    fields = {} if origin is None else record(value=annotation_value(native=origin))
    if origin is not None:
        keys(raw=fields, supported={"version", "name", "source", "kind", "terminology"})
        if fields.get("version") != "1":
            raise ValueError("Use a registered definition annotation version")
    title = text(value=raw.get("title", entry.name))
    explicit_name = None if origin is None else text(value=fields.get("name"))
    name, _ = LookupNamingPolicy.resolve_names(
        name=explicit_name, display_name=title if explicit_name else entry.name
    )
    return DefinitionMetadata(
        name=name,
        title=title,
        description=text(value=raw.get("description")),
        aliases=tuple(text(value=value) for value in items(value=raw.get("aliases", ()))),
        terminology=Terminology()
        if origin is None
        else wire_object(
            value=fields.get("terminology"),
            kind=Terminology,
        ),
        pin=None
        if origin is None
        else wire_object(value=fields.get("source"), kind=PinnedDefinitionReference),
        kind=None if origin is None else text(value=fields.get("kind")),
    ), entries


def origin(
    *,
    fragment: Fragment,
    dependencies: Sequence[SchemaDocument],
    iri: Iri | None,
    path: tuple[str | int, ...],
) -> SchemaOrigin:
    """Capture exact input bytes and definition locations for proposal review."""
    return SchemaOrigin(
        schema_iri=fragment.document.schema_iri,
        element_iri=iri,
        element_path=path,
        source_hash=fragment.document.content_hash,
        dependency_hashes=tuple(
            document.content_hash for document in dependencies if document != fragment.document
        ),
        mapping_version=LINKML_MAPPING.value,
    )
