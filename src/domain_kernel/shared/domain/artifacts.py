"""Typed metadata carried intact from a projection to its stored artifact."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.shared.contracts import ModelVersion, PinnedDefinitionReference
from domain_kernel.shared.domain.ontology_assets import Iri, OntologyClosurePin
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@unique
class SemanticGraphRole(StrEnum):
    """The graph addressed by a semantic document."""

    ONTOLOGY = "ontology"
    MODEL_METADATA = "model_metadata"
    MODEL_SHAPES = "model_shapes"
    INSTANCE_SHAPES = "instance_shapes"


@dataclass(frozen=True, kw_only=True)
class KeyEnforcementObligation:
    """Require the consumer to enforce the pinned owner's key."""

    owner: PinnedDefinitionReference
    key: KeyId
    kind: Literal["key_enforcement"] = "key_enforcement"

    def __post_init__(self) -> None:
        """Require the exact typed owner and key."""
        RuntimeTypeValidation.require_exact(
            value=self.owner, expected=PinnedDefinitionReference, field="Key owner"
        )
        RuntimeTypeValidation.require_exact(value=self.key, expected=KeyId, field="Key")
        _discriminator(value=self.kind, expected="key_enforcement")


@dataclass(frozen=True, kw_only=True)
class ReferenceTargetObligation:
    """Require the consumer to enforce a pinned reference target."""

    owner: PinnedDefinitionReference
    attribute: AttributeId
    kind: Literal["reference_target"] = "reference_target"

    def __post_init__(self) -> None:
        """Require the exact typed owner and attribute."""
        RuntimeTypeValidation.require_exact(
            value=self.owner, expected=PinnedDefinitionReference, field="Attribute owner"
        )
        RuntimeTypeValidation.require_exact(
            value=self.attribute, expected=AttributeId, field="Attribute"
        )
        _discriminator(value=self.kind, expected="reference_target")


@dataclass(frozen=True, kw_only=True)
class RelationshipEnforcementObligation:
    """Require the consumer to enforce a pinned relationship."""

    relationship: PinnedDefinitionReference
    kind: Literal["relationship_enforcement"] = "relationship_enforcement"

    def __post_init__(self) -> None:
        """Require the exact typed relationship reference."""
        RuntimeTypeValidation.require_exact(
            value=self.relationship, expected=PinnedDefinitionReference, field="Relationship"
        )
        _discriminator(value=self.kind, expected="relationship_enforcement")


@dataclass(frozen=True, kw_only=True)
class CollectionSemanticsObligation:
    """Require the consumer to apply the pinned field's collection semantics."""

    owner: PinnedDefinitionReference
    attribute: AttributeId
    kind: Literal["collection_semantics"] = "collection_semantics"

    def __post_init__(self) -> None:
        """Require the exact typed owner and attribute."""
        RuntimeTypeValidation.require_exact(
            value=self.owner, expected=PinnedDefinitionReference, field="Attribute owner"
        )
        RuntimeTypeValidation.require_exact(
            value=self.attribute, expected=AttributeId, field="Attribute"
        )
        _discriminator(value=self.kind, expected="collection_semantics")


def _discriminator(*, value: str, expected: str) -> None:
    RuntimeTypeValidation.require_exact(value=value, expected=str, field="Obligation kind")
    if value != expected:
        raise ValueError("Select the declared consumer obligation kind")


type ConsumerObligation = (
    KeyEnforcementObligation
    | ReferenceTargetObligation
    | RelationshipEnforcementObligation
    | CollectionSemanticsObligation
)
_OBLIGATION_TYPES = (
    KeyEnforcementObligation,
    ReferenceTargetObligation,
    RelationshipEnforcementObligation,
    CollectionSemanticsObligation,
)


@dataclass(frozen=True, kw_only=True)
class SemanticArtifactMetadata:
    """Identify a projected graph and the exact dependencies used to render it."""

    model: ModelVersion
    graph_iri: Iri
    role: SemanticGraphRole
    mapping_version: str
    ontology_dependencies: Sequence[OntologyClosurePin] = ()

    def __post_init__(self) -> None:
        """Validate graph scope and detach imported closure pins."""
        RuntimeTypeValidation.require_exact(
            value=self.model, expected=ModelVersion, field="Source version"
        )
        RuntimeTypeValidation.require_exact(value=self.graph_iri, expected=Iri, field="Graph IRI")
        RuntimeTypeValidation.require_exact(
            value=self.role, expected=SemanticGraphRole, field="Graph role"
        )
        TextValidation.require_text(value=self.mapping_version, field="Mapping version")
        object.__setattr__(
            self,
            "ontology_dependencies",
            SequenceValidation.snapshot_sequence(
                items=self.ontology_dependencies,
                item_type=OntologyClosurePin,
                field="Ontology dependencies",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class SchemaArtifactMetadata:
    """Identify the exact released schema selection and mapping."""

    model: ModelVersion
    document_iri: Iri
    mapping_version: str
    root: PinnedDefinitionReference | None = None

    def __post_init__(self) -> None:
        """Verify source and mapping identities."""
        RuntimeTypeValidation.require_exact(
            value=self.model, expected=ModelVersion, field="Schema source"
        )
        RuntimeTypeValidation.require_exact(
            value=self.document_iri, expected=Iri, field="Schema document IRI"
        )
        TextValidation.require_text(value=self.mapping_version, field="Schema mapping")
        if self.root is not None:
            RuntimeTypeValidation.require_exact(
                value=self.root, expected=PinnedDefinitionReference, field="Schema root"
            )
            if self.root.model.scope.project_id != self.model.scope.project_id:
                raise ValueError("Select a schema root in the publication's project")


@dataclass(frozen=True, kw_only=True)
class ProjectionMetadata:
    """Shared immutable metadata for payload, write request and artifact records."""

    projection_limits: Sequence[str] = ()
    semantic: SemanticArtifactMetadata | None = None
    schema: SchemaArtifactMetadata | None = None
    consumer_obligations: Sequence[ConsumerObligation] = ()

    def __post_init__(self) -> None:
        """Snapshot the metadata without normalizing away meaningful content."""
        limits = SequenceValidation.snapshot_sequence(
            items=self.projection_limits, item_type=str, field="Projection limits"
        )
        for limit in limits:
            TextValidation.require_text(value=limit, field="Projection limit")
        object.__setattr__(self, "projection_limits", limits)
        if self.semantic is not None:
            RuntimeTypeValidation.require_exact(
                value=self.semantic, expected=SemanticArtifactMetadata, field="Semantic metadata"
            )
        if self.schema is not None:
            RuntimeTypeValidation.require_exact(
                value=self.schema, expected=SchemaArtifactMetadata, field="Schema metadata"
            )
            if self.semantic is not None:
                raise ValueError("Select either graph or schema projection metadata")
        if not SequenceValidation.is_non_string_sequence(value=self.consumer_obligations) or any(
            type(item) not in _OBLIGATION_TYPES for item in self.consumer_obligations
        ):
            raise TypeError("Use a sequence of typed consumer obligations")
        object.__setattr__(self, "consumer_obligations", tuple(self.consumer_obligations))
