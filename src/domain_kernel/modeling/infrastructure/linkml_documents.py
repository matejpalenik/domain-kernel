"""Bounded optional syntax handling and the packaged LinkML primitive types."""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain_kernel.modeling.domain.interchange import (
    LINKML_MAPPING,
    LinkmlSyntax,
    MappingDescriptor,
)
from domain_kernel.modeling.domain.linkml import InvalidSchemaError, SchemaDocument
from domain_kernel.modeling.domain.portable_json import PortableReadError, read_portable_object
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.ontology_assets import Iri
from domain_kernel.shared.domain.ontology_errors import MissingDependencyError
from domain_kernel.shared.hashing import canonical_json_bytes, hash_bytes
from domain_kernel.shared.identifiers.content_hash import ContentHash

if TYPE_CHECKING:
    from collections.abc import Iterable

    from domain_kernel.shared.hashing import JsonValue

_TYPES = "linkml_model/model/schema/types.yaml"
_TYPES_HASH = ContentHash(
    value="sha256:1c79b264397bec0eadb404d22e9b163458f1b889809b3b482ecc39c98743fe00"
)
TYPES_IRI = Iri(value="https://w3id.org/linkml/types")
VOCABULARY = Iri(value="https://domain-kernel.invalid/vocabulary/dk-linkml/1.0#")
_DEPTH = 64
_MAX_EVENTS = 300_000
_YAML_TAG = "tag:yaml.org,2002:"


@runtime_checkable
class _Yaml(Protocol):
    def safe_dump(self, data: object, *, sort_keys: bool, allow_unicode: bool) -> str: ...
    def compose(self, stream: bytes) -> object: ...
    def parse(self, stream: bytes) -> Iterable[object]: ...


@runtime_checkable
class _Node(Protocol):
    @property
    def value(self) -> str | list[_Node] | list[tuple[_Node, _Node]]: ...
    @property
    def tag(self) -> str: ...


def invalid_schema(
    *, code: str, message: str, path: tuple[str | int, ...] = ()
) -> InvalidSchemaError:
    """Construct a safe syntax or dependency error."""
    return InvalidSchemaError(issues=(Issue(code=code, path=path, message=message),))


def adapter_mapping() -> MappingDescriptor:
    """Identify the exact optional dependencies without activating an import resolver."""
    try:
        versions = tuple(
            (name, version(distribution_name=name)) for name in ("linkml-runtime", "PyYAML")
        )
    except PackageNotFoundError:
        raise MissingDependencyError(message="Install the SDK's linkml extra.") from None
    return MappingDescriptor(
        id=LINKML_MAPPING,
        vocabulary_iri=VOCABULARY,
        supported_capabilities=(
            "flat_shapes",
            "static_vocabularies",
            "unit_annotations",
            "supplied_imports",
        ),
        adapter_versions=versions,
    )


def packaged_types() -> SchemaDocument:
    """Read the pinned primitive types from the installed optional package only."""
    try:
        payload = files("linkml_runtime").joinpath(*_TYPES.split("/")).read_bytes()
    except (OSError, ImportError) as error:
        raise MissingDependencyError(
            message="Install the packaged LinkML primitive types."
        ) from error
    if hash_bytes(content=payload) != _TYPES_HASH:
        raise invalid_schema(
            code="linkml_types_pin",
            message="Install the LinkML release with the registered types pin.",
        )
    return SchemaDocument(
        schema_iri=TYPES_IRI, syntax=LinkmlSyntax.YAML, payload=payload, content_hash=_TYPES_HASH
    )


def _yaml() -> _Yaml:
    try:
        module = import_module("yaml")
    except ImportError:
        raise MissingDependencyError(message="Install the SDK's linkml extra.") from None
    if not isinstance(module, _Yaml):
        raise MissingDependencyError(message="Install the supported YAML adapter.")
    return module


def _yaml_bounds(*, codec: _Yaml, payload: bytes) -> None:
    depth = 0
    for count, event in enumerate(codec.parse(payload), start=1):
        name = type(event).__name__
        if name == "AliasEvent" or count > _MAX_EVENTS:
            raise ValueError("Supply bounded YAML without aliases")
        if name in {"MappingStartEvent", "SequenceStartEvent"}:
            depth += 1
        if name in {"MappingEndEvent", "SequenceEndEvent"}:
            depth -= 1
        if depth > _DEPTH:
            raise ValueError("Supply bounded YAML nesting")


def _yaml_mapping(*, values: list[_Node] | list[tuple[_Node, _Node]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for entry in values:
        if not isinstance(entry, tuple):
            raise TypeError("Use key-value pairs in a YAML mapping")
        key, member = entry
        name = _yaml_value(node=key)
        if type(name) is not str or name in result:
            raise ValueError("Supply distinct text YAML keys")
        result[name] = _yaml_value(node=member)
    return result


def _yaml_scalar(*, kind: str, value: str) -> JsonValue:
    match kind:
        case "str":
            return value
        case "int":
            return int(value)
        case "bool" if value.lower() in ("true", "false"):
            return value.lower() == "true"
        case "null":
            return None
        case _:
            raise ValueError("Use a supported schema scalar")


def _yaml_value(*, node: object) -> JsonValue:
    if not isinstance(node, _Node):
        raise TypeError("Supply a declaration node")
    kind = node.tag.removeprefix(_YAML_TAG)
    value = node.value
    if isinstance(value, str):
        return _yaml_scalar(kind=kind, value=value)
    if kind == "map":
        return _yaml_mapping(values=value)
    if kind == "seq":
        return [_yaml_value(node=item) for item in value]
    raise ValueError("Use plain YAML mappings, arrays and scalar values")


def decode(*, document: SchemaDocument, max_bytes: int) -> dict[str, JsonValue]:
    """Verify bytes before parsing exactly one bounded JSON or YAML object."""
    if (
        len(document.payload) > max_bytes
        or hash_bytes(content=document.payload) != document.content_hash
    ):
        raise invalid_schema(
            code="schema_bytes", message="Supply bounded bytes matching the declared digest."
        )
    if document.syntax is LinkmlSyntax.JSON:
        try:
            return read_portable_object(
                payload=document.payload,
                expected_hash=document.content_hash,
                max_bytes=max_bytes,
                resource="LinkML schema",
                max_depth=_DEPTH,
            )
        except PortableReadError as error:
            raise InvalidSchemaError(issues=(error.issue,)) from None
    codec = _yaml()
    try:
        _yaml_bounds(codec=codec, payload=document.payload)
        content = _yaml_value(node=codec.compose(document.payload))
    except Exception:  # noqa: BLE001 - Sanitize errors crossing the optional parser boundary.
        raise invalid_schema(
            code="schema_yaml", message="Supply plain, bounded YAML with unique keys."
        ) from None
    if not isinstance(content, dict):
        raise invalid_schema(code="schema_yaml", message="Supply one YAML schema object.")
    return content


def encode(*, raw: dict[str, JsonValue], syntax: LinkmlSyntax) -> bytes:
    """Render only ordinary schema values in the requested portable syntax."""
    if syntax is LinkmlSyntax.JSON:
        return canonical_json_bytes(value=raw)
    return _yaml().safe_dump(raw, sort_keys=True, allow_unicode=True).encode("utf-8")
