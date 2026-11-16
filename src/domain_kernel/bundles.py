"""Portable public model releases and their structural integrity checks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    Definition,
    Process,
    require_definition_selector,
    typed_definition,
)
from domain_kernel._shared.domain.processes import ProcessDefinition
from domain_kernel.modeling.domain.bundle_shapes import bundle_schema, wire_shape
from domain_kernel.modeling.domain.errors.definition_errors import (
    DefinitionKindMismatchError,
    DefinitionNotFoundError,
)
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.publications import Approval, Publication
from domain_kernel.modeling.domain.snapshot_integrity import release_digest, verify_publication
from domain_kernel.publication.domain.identifiers.bundle_id import BundleId
from domain_kernel.shared.contracts import Issue, ModelScope, ModelVersion
from domain_kernel.shared.errors import (
    DomainKernelError,
    InvalidBundleError,
    UnsupportedBundleVersionError,
)
from domain_kernel.shared.hashing import canonical_json_bytes, hash_bytes
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.enums.model_kind import ModelKind
    from domain_kernel.modeling.domain.snapshots import ModelContent
    from domain_kernel.shared.hashing import JsonValue


@dataclass(frozen=True, kw_only=True)
class DomainModelBundle:
    """An immutable model release and the exact authorization it retains."""

    id: BundleId
    scope: ModelScope
    version: str
    publication: Publication
    approval: Approval
    content_hash: ContentHash
    published_at: datetime
    schema_version: Literal["1.0"] = "1.0"
    semantic_mapping_version: Literal["1.0"] = "1.0"
    format: Literal["domain-kernel.bundle"] = "domain-kernel.bundle"

    def __post_init__(self) -> None:
        """Reject incompatible release, preparation and authorization snapshots."""
        require_exact(value=self.id, expected=BundleId, field="Bundle ID")
        require_exact(value=self.scope, expected=ModelScope, field="Bundle scope")
        require_text(value=self.version, field="Release version")
        require_exact(value=self.publication, expected=Publication, field="Publication")
        require_exact(value=self.approval, expected=Approval, field="Release approval")
        require_exact(value=self.content_hash, expected=ContentHash, field="Bundle hash")
        require_text(value=self.semantic_mapping_version, field="Semantic mapping version")
        if (self.schema_version, self.format, self.semantic_mapping_version) != (
            "1.0",
            "domain-kernel.bundle",
            "1.0",
        ):
            raise ValueError("Use the registered bundle format and schema version")
        require_exact(value=self.published_at, expected=datetime, field="Release time")
        if self.published_at.utcoffset() is None:
            raise ValueError("Release time must include a time zone")
        publication = self.publication
        approval = self.approval
        if (
            not publication.ready
            or self.scope != publication.scope
            or self.scope != approval.scope
            or approval.publication_id != publication.id
            or approval.candidate_id != publication.candidate.id
            or approval.candidate_hash != publication.candidate.content_hash
            or approval.validation_id != publication.validation.id
            or approval.workspace_revision != publication.candidate.workspace_revision
            or approval.review_snapshot_version != publication.candidate.review_snapshot_version
            or approval.policy_fingerprint != publication.policy_fingerprint
            or not publication.prepared_at <= approval.approved_at <= self.published_at
        ):
            raise ValueError("Bundle approval must authorize this exact ready preparation")

    @property
    def model_version(self) -> ModelVersion:
        """Return the exact scope, release label and content pin."""
        return ModelVersion(scope=self.scope, version=self.version, content_hash=self.content_hash)

    @property
    def kind(self) -> ModelKind:
        """Return the model intent captured in the release."""
        return self.publication.candidate.kind

    @property
    def description(self) -> str:
        """Return the captured description of the released model."""
        return self.publication.candidate.description

    @property
    def content(self) -> ModelContent:
        """Return the immutable content captured in the publication."""
        return self.publication.candidate.content

    def _definition(self, *, name: str | None, definition_id: DefinitionId | None) -> Definition:
        require_definition_selector(name=name, item_id=definition_id, id_type=DefinitionId)
        for definition in (*self.content.definitions, *self.content.retired_definitions):
            if definition.id == definition_id or definition.name == name:
                return definition
        raise DefinitionNotFoundError

    def get_concept(
        self,
        *,
        name: str | None = None,
        concept_id: DefinitionId | None = None,
    ) -> Concept:
        """Read one exact active or retired concept and its immutable children."""
        value = self._definition(name=name, definition_id=concept_id)
        inspected = typed_definition(value=value, body_type=ConceptDefinition, view_type=Concept)
        if not isinstance(inspected, Concept):
            raise DefinitionKindMismatchError
        return inspected

    def get_process(
        self,
        *,
        name: str | None = None,
        process_id: DefinitionId | None = None,
    ) -> Process:
        """Read one active or retired process and its exact immutable parts."""
        value = self._definition(name=name, definition_id=process_id)
        inspected = typed_definition(value=value, body_type=ProcessDefinition, view_type=Process)
        if not isinstance(inspected, Process):
            raise DefinitionKindMismatchError
        return inspected

    @classmethod
    def from_approved(
        cls,
        *,
        publication: Publication,
        approval: Approval,
        bundle_id: BundleId,
        version: str,
        now: datetime,
    ) -> DomainModelBundle:
        """Construct a release with exact approval and authored content bindings."""
        return cls(
            id=bundle_id,
            scope=publication.scope,
            version=version,
            publication=publication,
            approval=approval,
            published_at=now,
            content_hash=release_digest(
                bundle_id=bundle_id,
                version=version,
                publication=publication,
                approval=approval,
                released_at=now,
            ),
        )

    def serialize(self) -> bytes:
        """Return the canonical UTF-8 JSON bytes for this complete release."""
        return _CODEC.serialize(bundle=self)

    @classmethod
    def deserialize(
        cls,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> DomainModelBundle:
        """Independently verify and load a portable model release."""
        return _CODEC.deserialize(payload=payload, expected_hash=expected_hash, max_bytes=max_bytes)

    @classmethod
    def get_json_schema(cls, *, schema_version: str = "1.0") -> str:
        """Return the complete closed JSON Schema for the exact wire version."""
        return _CODEC.schema(version=schema_version)


@dataclass(frozen=True, kw_only=True)
class BundleValidation:
    """Structural and content integrity observations from the built-in codec."""

    valid: bool
    schema_version: str
    issues: Sequence[Issue]

    def __post_init__(self) -> None:
        """Detach callers' issue collections."""
        require_exact(value=self.valid, expected=bool, field="Bundle validation outcome")
        require_text(value=self.schema_version, field="Bundle schema version")
        object.__setattr__(
            self,
            "issues",
            snapshot_sequence(items=self.issues, item_type=Issue, field="Issues"),
        )


def _invalid(*, code: str, message: str) -> InvalidBundleError:
    return InvalidBundleError(issues=(Issue(code=code, path=(), message=message),))


def _object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ValueError("Duplicate JSON fields")
    return values


def _invalid_number(_value: str) -> None:
    raise ValueError("Use the declared scalar lexical representation")


_MAX_DEPTH = 64


def _bounded_depth(*, document: JsonValue) -> None:
    stack = [(document, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise _invalid(
                code="bundle_depth", message="Use a bundle with at most 64 nested levels."
            )
        if isinstance(item, dict):
            stack.extend((part, depth + 1) for part in item.values())
        elif isinstance(item, Sequence) and is_non_string_sequence(item):
            stack.extend((part, depth + 1) for part in item)


def _input_bytes(*, payload: bytes | str, max_bytes: int) -> bytes:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("Set a positive integer byte limit")
    if type(payload) is str:
        if len(payload) > max_bytes:
            raise _invalid(
                code="bundle_size", message="Use a bundle within the configured byte limit."
            )
        try:
            payload = payload.encode("utf-8")
        except UnicodeError:
            raise _invalid(code="bundle_encoding", message="Use strictly valid UTF-8.") from None
    if type(payload) is not bytes:
        raise TypeError("Supply the bundle as bytes or text")
    if len(payload) > max_bytes:
        raise _invalid(code="bundle_size", message="Use a bundle within the configured byte limit.")
    return payload


def _wire_version(*, version: object) -> None:
    if type(version) is not str or version != "1.0":
        raise UnsupportedBundleVersionError


def _decode_document(*, content: bytes) -> dict[str, JsonValue]:
    try:
        # The stdlib decoder returns only validated JSON scalars, arrays and string-keyed objects.
        raw: JsonValue = json.loads(  # pyright: ignore[reportAny]
            content.decode("utf-8"),
            object_pairs_hook=_object,
            parse_float=_invalid_number,
            parse_constant=_invalid_number,
        )
    except (ValueError, RecursionError):
        raise _invalid(
            code="bundle_json", message="Supply strict UTF-8 JSON with unique fields."
        ) from None
    _bounded_depth(document=raw)
    if not isinstance(raw, dict) or raw.get("format") != "domain-kernel.bundle":
        raise _invalid(code="bundle_format", message="Load a complete Domain Kernel bundle.")
    if type(raw.get("schema_version")) is not str:
        raise _invalid(code="bundle_format", message="Include the exact supported schema version.")
    _wire_version(version=raw["schema_version"])
    return raw


def _parse_release(*, document: dict[str, JsonValue]) -> DomainModelBundle:
    shape = wire_shape(hint=DomainModelBundle)
    bundle = shape.parse(document)
    if type(bundle) is not DomainModelBundle:
        raise TypeError("Bundle root must be a release")
    if canonical_json_bytes(value=shape.render(bundle)) != canonical_json_bytes(value=document):
        raise ValueError("Use the declared scalar and bound representations")
    return bundle


class _BundleCodec:
    """Bind exact format selection, closed field decoding and semantic integrity."""

    def deserialize(
        self,
        *,
        payload: bytes | str,
        expected_hash: ContentHash | None,
        max_bytes: int,
    ) -> DomainModelBundle:
        content = _input_bytes(payload=payload, max_bytes=max_bytes)
        if expected_hash is not None:
            require_exact(value=expected_hash, expected=ContentHash, field="Transport hash")
            if hash_bytes(content=content) != expected_hash:
                raise _invalid(
                    code="transport_hash", message="Retrieve the exact expected bundle bytes."
                )
        raw = _decode_document(content=content)
        try:
            bundle = _parse_release(document=raw)
        except (TypeError, ValueError, DomainKernelError, ArithmeticError, RecursionError):
            raise _invalid(
                code="bundle_shape",
                message="Use the exact declared bundle fields and types.",
            ) from None
        require_valid_bundle(bundle=bundle)
        return bundle

    def serialize(self, *, bundle: DomainModelBundle) -> bytes:
        require_valid_bundle(bundle=bundle)
        return canonical_json_bytes(value=wire_shape(hint=DomainModelBundle).render(bundle))

    def validate(self, *, bundle: DomainModelBundle) -> BundleValidation:
        require_exact(value=bundle, expected=DomainModelBundle, field="Bundle")
        _wire_version(version=bundle.schema_version)
        issues = list(verify_publication(publication=bundle.publication))
        expected = release_digest(
            bundle_id=bundle.id,
            version=bundle.version,
            publication=bundle.publication,
            approval=bundle.approval,
            released_at=bundle.published_at,
        )
        if expected != bundle.content_hash:
            issues.append(
                Issue(
                    code="bundle_hash",
                    path=("content_hash",),
                    message="Retrieve the exact published content.",
                )
            )
        try:
            _ = canonical_json_bytes(value=wire_shape(hint=DomainModelBundle).render(bundle))
        except (TypeError, ValueError, ArithmeticError, RecursionError):
            issues.append(
                Issue(code="bundle_shape", path=(), message="Use the exact declared bundle fields.")
            )
        return BundleValidation(
            valid=not issues, schema_version=bundle.schema_version, issues=issues
        )

    def schema(self, *, version: str) -> str:
        _wire_version(version=version)
        return canonical_json_bytes(value=bundle_schema(root=DomainModelBundle)).decode("utf-8")


_CODEC = _BundleCodec()


def validate_bundle(*, bundle: DomainModelBundle) -> BundleValidation:
    """Check complete structural, reference and release integrity without I/O."""
    return _CODEC.validate(bundle=bundle)


def require_valid_bundle(*, bundle: DomainModelBundle) -> None:
    """Require a trustworthy structural snapshot before using it in an operation."""
    result = validate_bundle(bundle=bundle)
    if not result.valid:
        raise InvalidBundleError(issues=result.issues)
