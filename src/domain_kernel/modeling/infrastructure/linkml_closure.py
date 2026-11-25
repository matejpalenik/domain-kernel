"""Verify supplied LinkML schema closure before interpreting any declaration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.infrastructure.linkml_documents import (
    TYPES_IRI,
    decode,
    invalid_schema,
    packaged_types,
)
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.linkml import SchemaDocument
    from domain_kernel.shared.hashing import JsonValue

_GROUPS = ("classes", "slots", "types", "enums")
_ELEMENT_IRI = {
    "classes": "class_uri",
    "slots": "slot_uri",
    "types": "uri",
    "enums": "enum_uri",
}
_MAX_DOCUMENTS = 64
_MAX_DEPTH = 16


def record(*, value: JsonValue) -> dict[str, JsonValue]:
    """Require a plain JSON-shaped mapping."""
    if not isinstance(value, dict):
        raise TypeError("Supply a mapping for this declaration")
    return value


def text(*, value: JsonValue) -> str:
    """Require nonblank text without coercion."""
    if type(value) is not str or not value.strip():
        raise TypeError("Supply the declared text value")
    return value


def items(*, value: JsonValue) -> tuple[JsonValue, ...]:
    """Snapshot a native list of values."""
    if not SequenceValidation.is_non_string_sequence(value=value):
        raise TypeError("Supply a sequence for this declaration")
    if not isinstance(value, (tuple, list)):
        raise TypeError("Supply a portable array for this declaration")
    return tuple(value)


def expanded(*, raw: JsonValue, prefixes: dict[str, str]) -> Iri:
    """Resolve declared CURIEs and absolute identifiers with no path fallback."""
    value = text(value=raw)
    prefix, colon, suffix = value.partition(":")
    if not colon or not suffix:
        raise ValueError("Supply an absolute IRI or an explicitly declared CURIE")
    if suffix.startswith("//") or prefix in ("urn", "tag"):
        return Iri(value=value)
    if prefix not in prefixes:
        raise ValueError("Declare the prefix for this schema identifier")
    return Iri(value=prefixes[prefix] + suffix)


@dataclass(frozen=True, kw_only=True)
class Fragment:
    """One inspected schema with its exact original bytes and prefix bindings."""

    document: SchemaDocument
    raw: dict[str, JsonValue]
    prefixes: dict[str, str]
    imports: tuple[Iri, ...]

    def element_iri(self, *, group: str, raw: dict[str, JsonValue], name: str) -> Iri | None:
        """Retrieve an explicit element identity or its declared prefix mapping."""
        explicit = raw.get(_ELEMENT_IRI[group])
        if group == "types" and "type_uri" in raw:
            alternate = expanded(raw=raw["type_uri"], prefixes=self.prefixes)
            if explicit is not None and expanded(raw=explicit, prefixes=self.prefixes) != alternate:
                raise ValueError("Use a consistent type declaration IRI")
            return alternate
        if explicit is not None:
            return expanded(raw=explicit, prefixes=self.prefixes)
        if self.raw.get("default_prefix") is None:
            return None
        prefix = text(value=self.raw["default_prefix"])
        return expanded(raw=f"{prefix}:{name}", prefixes=self.prefixes)


@dataclass(frozen=True, kw_only=True)
class Entry:
    """One native declaration with every exact source location."""

    name: str
    raw: dict[str, JsonValue]
    iri: Iri | None
    fragments: tuple[Fragment, ...]


@dataclass(frozen=True, kw_only=True)
class SchemaClosure:
    """Verified local declarations from explicitly supplied input documents."""

    fragments: tuple[Fragment, ...]
    dependencies: tuple[SchemaDocument, ...]
    entries: dict[tuple[str, str], Entry]


def _fragment(*, document: SchemaDocument, max_bytes: int) -> Fragment:
    raw = decode(document=document, max_bytes=max_bytes)
    try:
        prefixes = {
            key: Iri(value=text(value=value)).value
            for key, value in record(value=raw.get("prefixes", {})).items()
        }
        if "linkml" in prefixes and prefixes["linkml"] != "https://w3id.org/linkml/":
            raise invalid_schema(
                code="schema_builtin_prefix", message="Use the canonical built-in LinkML prefix."
            )
        effective = {"linkml": "https://w3id.org/linkml/", **prefixes}
        if expanded(raw=raw.get("id"), prefixes=effective) != document.schema_iri:
            raise invalid_schema(
                code="schema_iri_mismatch", message="Use the exact expanded schema envelope IRI."
            )
        imports = tuple(
            expanded(raw=item, prefixes=effective) for item in items(value=raw.get("imports", ()))
        )
        if len(set(imports)) != len(imports):
            raise invalid_schema(
                code="schema_import_duplicate", message="Supply each dependency once."
            )
    except (ValueError, TypeError):
        raise invalid_schema(
            code="schema_identity",
            message="Use exact expanded schema IDs and declared import IRIs.",
        ) from None
    return Fragment(document=document, raw=raw, prefixes=effective, imports=imports)


def _reachable(*, start: Iri, fragments: dict[Iri, Fragment]) -> tuple[tuple[Fragment, ...], bool]:
    checked: dict[Iri, Fragment] = {}
    active: set[Iri] = set()
    uses_types = False

    def visit(*, target: Iri) -> None:
        nonlocal uses_types
        if target == TYPES_IRI:
            uses_types = True
            return
        if target in active or len(active) >= _MAX_DEPTH:
            raise invalid_schema(
                code="schema_import_cycle", message="Use a bounded acyclic import closure."
            )
        if target in checked:
            return
        if target not in fragments:
            raise invalid_schema(
                code="schema_import_missing", message="Supply each exact imported schema."
            )
        node = fragments[target]
        active.add(target)
        for child in node.imports:
            visit(target=child)
        active.remove(target)
        checked[target] = node

    visit(target=start)
    if checked.keys() != fragments.keys():
        raise invalid_schema(
            code="schema_import_unused", message="Supply only explicitly imported documents."
        )
    return tuple(checked.values()), uses_types


def _merge(*, fragments: tuple[Fragment, ...]) -> dict[tuple[str, str], Entry]:
    prefixes: dict[str, str] = {}
    entries: dict[tuple[str, str], Entry] = {}
    by_iri: dict[Iri, tuple[str, str]] = {}
    try:
        for fragment in fragments:
            for name, value in fragment.prefixes.items():
                if prefixes.setdefault(name, value) != value:
                    raise invalid_schema(
                        code="schema_prefix_conflict",
                        message="Use consistent prefixes throughout the supplied closure.",
                    )
            for group in _GROUPS:
                for name, raw in record(value=fragment.raw.get(group, {})).items():
                    spec = record(value=raw)
                    key = (group, name)
                    iri = fragment.element_iri(group=group, raw=spec, name=name)
                    if iri is not None and by_iri.setdefault(iri, key) != key:
                        raise invalid_schema(
                            code="schema_element_iri_conflict",
                            message="Supply globally distinct expanded declaration IRIs.",
                        )
                    existing = entries.get(key)
                    if existing is not None and (existing.iri != iri or existing.raw != spec):
                        raise invalid_schema(
                            code="schema_declaration_conflict",
                            message="Resolve differing declarations of the same schema name.",
                        )
                    origins = () if existing is None else existing.fragments
                    entries[key] = Entry(
                        name=name, raw=spec, iri=iri, fragments=(*origins, fragment)
                    )
    except (TypeError, ValueError):
        raise invalid_schema(
            code="schema_import_conflict",
            message="Check the declaration fields and expanded IRIs.",
        ) from None
    return entries


def verify_closure(
    *, document: SchemaDocument, dependencies: Sequence[SchemaDocument], max_bytes: int
) -> SchemaClosure:
    """Read all and only the exact declared closure, without external resolution."""
    supplied = (document, *dependencies)
    if len(supplied) > _MAX_DOCUMENTS or sum(len(item.payload) for item in supplied) > max_bytes:
        raise invalid_schema(
            code="schema_limit", message="Supply a smaller schema dependency closure."
        )
    parsed: dict[Iri, Fragment] = {}
    for item in supplied:
        if item.schema_iri == TYPES_IRI or item.schema_iri in parsed:
            raise invalid_schema(
                code="schema_import_duplicate", message="Supply distinct non-built-in schemas."
            )
        parsed[item.schema_iri] = _fragment(document=item, max_bytes=max_bytes)
    ordered, uses_types = _reachable(start=document.schema_iri, fragments=parsed)
    verified = tuple(item.document for item in ordered if item.document != document)
    if uses_types:
        verified = (*verified, packaged_types())
    return SchemaClosure(
        fragments=ordered, dependencies=verified, entries=_merge(fragments=ordered)
    )
