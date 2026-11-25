"""Immutable views over exact published model identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.snapshots import DomainModelBundle
from domain_kernel.reference_packs.domain.packs import ReferencePack
from domain_kernel.shared.contracts import Issue, ModelVersion, PinnedDefinitionReference
from domain_kernel.shared.domain.definitions import Definition
from domain_kernel.shared.domain.ontology_closure import OntologyClosure
from domain_kernel.shared.domain.record_encoding import record_value
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence


@unique
class TraversalDirection(StrEnum):
    """Follow graph edges in the chosen direction when selecting a view."""

    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


def composition_digest(
    *,
    roots: Sequence[ModelVersion],
    bundles: Sequence[DomainModelBundle],
) -> ContentHash:
    """Bind the original roots and complete exact closure."""
    return hash_json(
        value=record_value(
            value=("composition-v1", roots, tuple(item.model_version for item in bundles)),
        ),
    )


@dataclass(frozen=True, kw_only=True)
class ModelComposition:
    """Read-only assembly of publications and their original approvals."""

    roots: Sequence[ModelVersion]
    bundles: Sequence[DomainModelBundle]
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Freeze exact roots and release records before graph selection."""
        roots = snapshot_sequence(items=self.roots, item_type=ModelVersion, field="Roots")
        bundles = snapshot_sequence(
            items=self.bundles,
            item_type=DomainModelBundle,
            field="Bundles",
        )
        pins = {item.model_version for item in bundles}
        if not roots or not set(roots) <= pins or len(set(roots)) != len(roots):
            raise ValueError("Select distinct roots from the materialized composition")
        if len({item.scope for item in bundles}) != len(bundles):
            raise ValueError("Materialize one exact publication per composed model")
        require_exact(value=self.content_hash, expected=ContentHash, field="Composition hash")
        if self.content_hash != composition_digest(roots=roots, bundles=bundles):
            raise ValueError("Retain the exact composition digest")
        object.__setattr__(self, "roots", roots)
        object.__setattr__(self, "bundles", bundles)


@dataclass(frozen=True, kw_only=True)
class SliceDefinition:
    """An inspected definition with its owning publication and exact revision."""

    reference: PinnedDefinitionReference
    definition: Definition

    def __post_init__(self) -> None:
        """Require a definition bound to the exact qualified identity."""
        require_exact(value=self.reference, expected=PinnedDefinitionReference, field="Reference")
        require_exact(value=self.definition, expected=Definition, field="Definition")
        if (
            self.reference.model.scope != self.definition.scope
            or self.reference.definition_id != self.definition.id
            or self.reference.definition_revision != self.definition.revision
        ):
            raise ValueError("Materialize the exact qualified definition")


@dataclass(frozen=True, kw_only=True)
class ModelSlice:
    """A read-only selection and the complete required supporting graph."""

    composition_hash: ContentHash
    models: Sequence[ModelVersion]
    seeds: Sequence[PinnedDefinitionReference]
    selected: Sequence[SliceDefinition]
    support: Sequence[SliceDefinition]
    reference_packs: Sequence[ReferencePack]
    max_hops: int
    direction: TraversalDirection
    content_hash: ContentHash
    issues: Sequence[Issue] = ()
    ontologies: Sequence[OntologyClosure] = ()

    def __post_init__(self) -> None:
        """Detach inventories and retain the exact selection and limits."""
        require_exact(value=self.composition_hash, expected=ContentHash, field="Composition hash")
        require_exact(value=self.content_hash, expected=ContentHash, field="Slice hash")
        require_exact(
            value=self.direction, expected=TraversalDirection, field="Traversal direction"
        )
        require_exact(value=self.max_hops, expected=int, field="Hop limit")
        if self.max_hops < 0:
            raise ValueError("Use a nonnegative hop limit")
        for field, items, kind in (
            ("models", self.models, ModelVersion),
            ("seeds", self.seeds, PinnedDefinitionReference),
            ("selected", self.selected, SliceDefinition),
            ("support", self.support, SliceDefinition),
            ("reference_packs", self.reference_packs, ReferencePack),
            ("ontologies", self.ontologies, OntologyClosure),
            ("issues", self.issues, Issue),
        ):
            object.__setattr__(
                self, field, snapshot_sequence(items=items, item_type=kind, field=field)
            )
