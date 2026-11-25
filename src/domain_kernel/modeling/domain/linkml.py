"""Portable LinkML schema documents and immutable import/projection results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Literal

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.interchange import (
    IdentityBinding,
    LinkmlSyntax,
    MappingDescriptor,
)
from domain_kernel.shared.contracts import Issue, ModelVersion, PinnedDefinitionReference
from domain_kernel.shared.domain.artifacts import ProjectionMetadata
from domain_kernel.shared.domain.authoring import ModelChangePlan
from domain_kernel.shared.domain.definitions import ValueSetDefinition
from domain_kernel.shared.domain.model_values import ValueSetMembership
from domain_kernel.shared.domain.ontology_assets import Iri
from domain_kernel.shared.domain.schema_origins import SchemaOrigin
from domain_kernel.shared.errors import CodedDomainError
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.artifacts import ConsumerObligation


class InvalidSchemaError(CodedDomainError):
    """The exact supplied schema or dependency graph could not be loaded."""

    _error_code: ClassVar[str] = "invalid_schema"
    issues: tuple[Issue, ...]

    def __init__(self, *, issues: Sequence[Issue]) -> None:
        """Preserve safe diagnostics without retaining parser payloads."""
        self.issues = SequenceValidation.snapshot_sequence(
            items=issues, item_type=Issue, field="Schema issues"
        )
        super().__init__(message="Supply the exact schema bytes and its declared dependencies.")


@dataclass(frozen=True, kw_only=True)
class SchemaDocument:
    """A declared LinkML schema ID, syntax and exact-byte digest."""

    schema_iri: Iri
    syntax: LinkmlSyntax
    payload: bytes = field(repr=False)
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Verify the transport envelope's nominal fields."""
        RuntimeTypeValidation.require_exact(value=self.schema_iri, expected=Iri, field="Schema IRI")
        RuntimeTypeValidation.require_exact(
            value=self.syntax, expected=LinkmlSyntax, field="LinkML syntax"
        )
        RuntimeTypeValidation.require_exact(
            value=self.payload, expected=bytes, field="Schema bytes"
        )
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Schema digest"
        )


@dataclass(frozen=True, kw_only=True)
class OpenValueSetAnnotation:
    """Known codes and SDK bindings on a permissive named LinkML string type."""

    source: PinnedDefinitionReference
    body: ValueSetDefinition
    version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        """Require the declared version and an open value-set body."""
        RuntimeTypeValidation.require_exact(
            value=self.source, expected=PinnedDefinitionReference, field="Value-set pin"
        )
        RuntimeTypeValidation.require_exact(
            value=self.body, expected=ValueSetDefinition, field="Open value set"
        )
        RuntimeTypeValidation.require_exact(
            value=self.version, expected=str, field="Open value-set annotation version"
        )
        if self.version != "1" or self.body.membership is not ValueSetMembership.OPEN:
            raise ValueError("Use a supported annotation of an open value set")


@dataclass(frozen=True, kw_only=True)
class LinkmlProjection:
    """A delivered schema and the exact shape selection it represents."""

    model: ModelVersion
    mapping: MappingDescriptor
    schema: SchemaDocument
    dependencies: Sequence[SchemaDocument]
    selected: Sequence[PinnedDefinitionReference]
    excluded_definition_ids: Sequence[DefinitionId]
    identities: Sequence[IdentityBinding]
    issues: Sequence[Issue]
    consumer_obligations: Sequence[ConsumerObligation] = ()

    def __post_init__(self) -> None:
        """Keep exact transport and selection metadata immutable."""
        RuntimeTypeValidation.require_exact(value=self.model, expected=ModelVersion, field="Model")
        RuntimeTypeValidation.require_exact(
            value=self.mapping, expected=MappingDescriptor, field="Mapping"
        )
        RuntimeTypeValidation.require_exact(
            value=self.schema, expected=SchemaDocument, field="LinkML schema"
        )
        for name, items, kind in (
            ("dependencies", self.dependencies, SchemaDocument),
            ("selected", self.selected, PinnedDefinitionReference),
            ("excluded_definition_ids", self.excluded_definition_ids, DefinitionId),
            ("identities", self.identities, IdentityBinding),
            ("issues", self.issues, Issue),
        ):
            object.__setattr__(
                self,
                name,
                SequenceValidation.snapshot_sequence(items=items, item_type=kind, field=name),
            )
        obligations = ProjectionMetadata(consumer_obligations=self.consumer_obligations)
        object.__setattr__(self, "consumer_obligations", obligations.consumer_obligations)


@dataclass(frozen=True, kw_only=True)
class SchemaImportResult:
    """A proposed authoring plan or explicit diagnostics for an unsupported shape."""

    plan: ModelChangePlan | None
    mapping: MappingDescriptor
    origins: Sequence[SchemaOrigin]
    issues: Sequence[Issue]

    def __post_init__(self) -> None:
        """Detach the analysis and reject a plan with unresolved errors."""
        if self.plan is not None:
            RuntimeTypeValidation.require_exact(
                value=self.plan, expected=ModelChangePlan, field="Import plan"
            )
            if self.issues:
                raise ValueError("Resolve the schema findings before proposing changes")
        RuntimeTypeValidation.require_exact(
            value=self.mapping, expected=MappingDescriptor, field="Mapping"
        )
        object.__setattr__(
            self,
            "origins",
            SequenceValidation.snapshot_sequence(
                items=self.origins, item_type=SchemaOrigin, field="Origins"
            ),
        )
        object.__setattr__(
            self,
            "issues",
            SequenceValidation.snapshot_sequence(
                items=self.issues, item_type=Issue, field="Issues"
            ),
        )
