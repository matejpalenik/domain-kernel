"""Immutable reference definitions, authored patterns and composition provenance."""

from __future__ import annotations

from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from enum import StrEnum, unique
from typing import TYPE_CHECKING, ClassVar, Self
from uuid import uuid4

from domain_kernel._shared.domain.definitions import require_definition_body
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import require_lookup_name, resolve_names
from domain_kernel._shared.domain.ontology_assets import OntologyTermReference
from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.models import ReferencePackPin
from domain_kernel.reference_packs.domain.identifiers.pattern_id import PatternId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import DefinitionBody


COVERAGE_VALIDATOR = "domain-kernel.coverage@1.0"


@unique
class ReferenceAssetKind(StrEnum):
    """Kind of an explicitly supplied reference asset."""

    ONTOLOGY = "ontology"
    DEFINITIONS = "definitions"
    PATTERNS = "patterns"
    REFERENCE_PACK = "reference_pack"


@unique
class ObligationKind(StrEnum):
    """Meaning of an individual authored pack obligation."""

    COVERAGE = "coverage"
    DEFINITION = "definition"
    ALIGNMENT = "alignment"
    PROCESS = "process"
    DECISION = "decision"
    CONFIRMATION = "confirmation"
    SEMANTIC = "semantic"


@unique
class MappingRelation(StrEnum):
    """Business relationship of a local meaning to an inspected reference."""

    EQUIVALENT = "equivalent"
    NARROWER = "narrower"
    BROADER = "broader"
    RELATED = "related"
    DISTINCT = "distinct"


@dataclass(frozen=True, kw_only=True)
class ReferenceAlignment:
    """One explicitly reviewed business relationship to an exact pack member."""

    reference_id: ReferenceDefinitionId
    reference_pack: ReferencePackPin
    relation: MappingRelation
    reason: str

    def __post_init__(self) -> None:
        """Require the exact object pin and a host-provided rationale."""
        require_exact(value=self.reference_id, expected=ReferenceDefinitionId, field="Reference ID")
        require_exact(value=self.reference_pack, expected=ReferencePackPin, field="Reference pack")
        require_exact(value=self.relation, expected=MappingRelation, field="Business relation")
        require_text(value=self.reason, field="Mapping reason")


@unique
class PackMaturity(StrEnum):
    """Declared authoring status of a reference pack."""

    EXPERIMENTAL = "experimental"
    REVIEWED = "reviewed"


@dataclass(frozen=True, kw_only=True)
class ReferenceOrigin:
    """A definition's exact upstream identity before namespacing."""

    reference_pack: ReferencePackPin
    definition_id: ReferenceDefinitionId

    def __post_init__(self) -> None:
        """Require the exact source pack and nominal definition pins."""
        require_exact(value=self.reference_pack, expected=ReferencePackPin, field="Origin pack")
        require_exact(value=self.definition_id, expected=ReferenceDefinitionId, field="Origin ID")


@dataclass(frozen=True, kw_only=True)
class ReferenceDefinition:
    """An attributed definition in a reference graph."""

    id: ReferenceDefinitionId
    name: str
    meaning: str
    body: DefinitionBody
    provenance: str
    origins: Sequence[ReferenceOrigin] = ()
    ontology_terms: Sequence[OntologyTermReference] = ()
    terminology: Terminology = dataclass_field(default_factory=Terminology)
    _pack: ClassVar[ReferencePackPin | None] = None

    def __post_init__(self) -> None:
        """Freeze verified reference metadata and preserve the explicit body."""
        require_exact(
            value=self.id, expected=ReferenceDefinitionId, field="Reference definition ID"
        )
        require_lookup_name(name=self.name)
        require_text(value=self.meaning, field="Reference meaning")
        require_text(value=self.provenance, field="Reference provenance")
        require_definition_body(body=self.body)
        require_exact(value=self.terminology, expected=Terminology, field="Terminology")
        object.__setattr__(
            self,
            "origins",
            snapshot_sequence(
                items=self.origins,
                item_type=ReferenceOrigin,
                field="Reference origins",
            ),
        )
        object.__setattr__(
            self,
            "ontology_terms",
            snapshot_sequence(
                items=self.ontology_terms,
                item_type=OntologyTermReference,
                field="Reference ontology terms",
            ),
        )

    @property
    def reference_pack(self) -> ReferencePackPin | None:
        """Expose the exact containing pack context, when materialized."""
        return self._pack

    def associate(self, *, pin: ReferencePackPin) -> ReferenceDefinition:
        """Attach containing context to an immutable copy of this member."""
        if self._pack == pin:
            return self
        member = replace(self)
        object.__setattr__(member, "_pack", pin)
        return member


@dataclass(frozen=True, kw_only=True)
class ReferencePackDependency:
    """Provenance and exact identity for one selected upstream asset."""

    key: str
    version: str
    content_hash: ContentHash
    kind: ReferenceAssetKind
    provenance: str
    license: str

    def __post_init__(self) -> None:
        """Retain explicit attribution and exact digest metadata."""
        for field, value in (
            ("Dependency key", self.key),
            ("Dependency version", self.version),
            ("Dependency provenance", self.provenance),
            ("Dependency license", self.license),
        ):
            require_text(value=value, field=field)
        require_exact(value=self.content_hash, expected=ContentHash, field="Dependency hash")
        require_exact(value=self.kind, expected=ReferenceAssetKind, field="Dependency kind")


@dataclass(frozen=True, kw_only=True)
class ReferencePackObligation:
    """An explicit rule or coverage expectation imported at the author's direction."""

    id: ObligationId
    description: str
    kind: ObligationKind
    required: bool
    reference_ids: Sequence[ReferenceDefinitionId]
    validator_id: str

    def __post_init__(self) -> None:
        """Keep the exact validator, requiredness and detached target list."""
        require_exact(value=self.id, expected=ObligationId, field="Obligation ID")
        require_exact(value=self.kind, expected=ObligationKind, field="Obligation kind")
        require_exact(value=self.required, expected=bool, field="Obligation requiredness")
        require_text(value=self.description, field="Obligation description")
        require_text(value=self.validator_id, field="Obligation validator ID")
        refs = snapshot_sequence(
            items=self.reference_ids,
            item_type=ReferenceDefinitionId,
            field="Obligation references",
        )
        if len(set(refs)) != len(refs):
            raise ValueError("Select each obligation reference once")
        object.__setattr__(self, "reference_ids", refs)


@dataclass(frozen=True, kw_only=True, init=False)
class Pattern:
    """A reusable authored graph and its stable pack-local lookup name."""

    id: PatternId
    name: str
    display_name: str
    definitions: tuple[ReferenceDefinition, ...]
    entrypoint_ids: tuple[ReferenceDefinitionId, ...]
    description: str
    _pack: ClassVar[ReferencePackPin | None] = None

    def __init__(
        self,
        *,
        definitions: Sequence[ReferenceDefinition],
        entrypoint_ids: Sequence[ReferenceDefinitionId],
        description: str,
        display_name: str | None = None,
        name: str | None = None,
    ) -> None:
        """Generate a fresh pattern identity once."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        self._initialize(
            identity=PatternId(value=uuid4().hex),
            name=lookup,
            display_name=label,
            definitions=definitions,
            entrypoint_ids=entrypoint_ids,
            description=description,
        )

    def _initialize(  # noqa: PLR0913 - Store the exact declared snapshot.
        self,
        *,
        identity: PatternId,
        name: str,
        display_name: str,
        definitions: Sequence[ReferenceDefinition],
        entrypoint_ids: Sequence[ReferenceDefinitionId],
        description: str,
    ) -> None:
        require_exact(value=identity, expected=PatternId, field="Pattern ID")
        require_lookup_name(name=name)
        require_text(value=display_name, field="Pattern label")
        require_text(value=description, field="Pattern description")
        object.__setattr__(self, "id", identity)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "description", description)
        object.__setattr__(
            self,
            "definitions",
            snapshot_sequence(
                items=definitions,
                item_type=ReferenceDefinition,
                field="Pattern definitions",
            ),
        )
        object.__setattr__(
            self,
            "entrypoint_ids",
            snapshot_sequence(
                items=entrypoint_ids,
                item_type=ReferenceDefinitionId,
                field="Pattern entry points",
            ),
        )

    @classmethod
    def restore(  # noqa: PLR0913 - Each keyword is an exact field in the closed record.
        cls,
        *,
        id: PatternId,  # noqa: A002 - Match the stored field name.
        name: str,
        display_name: str,
        definitions: Sequence[ReferenceDefinition],
        entrypoint_ids: Sequence[ReferenceDefinitionId],
        description: str,
    ) -> Self:
        """Restore the exact stored pattern without generating a new identity."""
        pattern = cls.__new__(cls)
        pattern._initialize(  # noqa: SLF001 - Restore this exact frozen pattern.
            identity=id,
            name=name,
            display_name=display_name,
            definitions=definitions,
            entrypoint_ids=entrypoint_ids,
            description=description,
        )
        return pattern

    @property
    def reference_pack(self) -> ReferencePackPin | None:
        """Expose the exact containing pack independently of upstream origin."""
        return self._pack

    def associate(self, *, pin: ReferencePackPin) -> Pattern:
        """Associate a detached pattern and its members with a verified pin."""
        if self._pack == pin:
            return self
        member = Pattern.restore(
            id=self.id,
            name=self.name,
            display_name=self.display_name,
            definitions=tuple(value.associate(pin=pin) for value in self.definitions),
            entrypoint_ids=self.entrypoint_ids,
            description=self.description,
        )
        object.__setattr__(member, "_pack", pin)
        return member


@dataclass(frozen=True, kw_only=True)
class ReferencePackImportManifest:
    """Retained upstream pins, selections and complete omissions."""

    reference_pack: ReferencePackPin
    namespace: str
    pattern_ids: Sequence[PatternId]
    obligation_ids: Sequence[ObligationId]
    omitted_obligations: Sequence[ReferencePackObligation]

    def __post_init__(self) -> None:
        """Detach the exact original selected and omitted members."""
        require_exact(value=self.reference_pack, expected=ReferencePackPin, field="Source pack")
        require_text(value=self.namespace, field="Import namespace")
        for field, items, kind in (
            ("pattern_ids", self.pattern_ids, PatternId),
            ("obligation_ids", self.obligation_ids, ObligationId),
            ("omitted_obligations", self.omitted_obligations, ReferencePackObligation),
        ):
            object.__setattr__(
                self, field, snapshot_sequence(items=items, item_type=kind, field=field)
            )


@dataclass(frozen=True, kw_only=True)
class ReferencePackComposition:
    """Attributed composition intent retained in the immutable result."""

    imports: Sequence[ReferencePackImportManifest]
    actor: str
    reason: str

    def __post_init__(self) -> None:
        """Record all source selections under an explicit actor and reason."""
        require_text(value=self.actor, field="Composition actor")
        require_text(value=self.reason, field="Composition reason")
        object.__setattr__(
            self,
            "imports",
            snapshot_sequence(
                items=self.imports,
                item_type=ReferencePackImportManifest,
                field="Pack imports",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ReferencePackValidation:
    """Complete structural findings and required runtime capabilities."""

    valid: bool
    issues: Sequence[Issue]
    required_capabilities: Sequence[str]

    def __post_init__(self) -> None:
        """Detach findings and keep capability identities immutable."""
        require_exact(value=self.valid, expected=bool, field="Pack validation result")
        object.__setattr__(
            self,
            "issues",
            snapshot_sequence(
                items=self.issues,
                item_type=Issue,
                field="Pack findings",
            ),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            snapshot_sequence(
                items=self.required_capabilities,
                item_type=str,
                field="Required capabilities",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class DefinitionBinding:
    """Explicitly reuse an exact inspected local definition for a reference member."""

    reference_id: ReferenceDefinitionId
    definition_id: DefinitionId
    definition_revision: int

    def __post_init__(self) -> None:
        """Pin both identities and require a positive local revision."""
        require_exact(value=self.reference_id, expected=ReferenceDefinitionId, field="Reference ID")
        require_exact(value=self.definition_id, expected=DefinitionId, field="Local ID")
        require_exact(value=self.definition_revision, expected=int, field="Local revision")
        if self.definition_revision < 1:
            raise ValueError("Bind an exact positive local revision")


@dataclass(frozen=True, kw_only=True)
class PatternAdoption:
    """Record the exact source pattern, selected pack and local correspondence."""

    reference_pack: ReferencePackPin
    pattern: Pattern
    definitions: Sequence[DefinitionBinding]

    def __post_init__(self) -> None:
        """Restore shared runtime context from the explicit pack pin."""
        require_exact(
            value=self.reference_pack, expected=ReferencePackPin, field="Adoption pack pin"
        )
        require_exact(value=self.pattern, expected=Pattern, field="Adopted pattern")
        if self.pattern.reference_pack not in (None, self.reference_pack):
            raise ValueError("Use the exact pattern's containing pack")
        object.__setattr__(self, "pattern", self.pattern.associate(pin=self.reference_pack))
        definitions = snapshot_sequence(
            items=self.definitions,
            item_type=DefinitionBinding,
            field="Adopted definitions",
        )
        if {item.reference_id for item in definitions} != {
            item.id for item in self.pattern.definitions
        } or len({item.definition_id for item in definitions}) != len(definitions):
            raise ValueError("Retain one distinct local correspondence per adopted member")
        object.__setattr__(self, "definitions", definitions)
