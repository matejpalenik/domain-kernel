"""Captured evidence and unapproved mappings for evidence-led schema discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import date

    from domain_kernel.discovery.domain.bindings import BindingWitness
    from domain_kernel.discovery.domain.schema_options import (
        CompetencyQuestion,
        DiscoverySourceContext,
    )
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.reference_packs.domain.contracts import MappingRelation
    from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
        ReferenceDefinitionId,
    )


type ObservationModality = Literal[
    "descriptive", "rule", "causal", "suspected", "temporal", "negated", "assumed"
]


@dataclass(frozen=True, kw_only=True)
class SchemaRecordBinding:
    """Verified role witnesses and the anchor for their owning source record."""

    anchor: BindingWitness
    source: BindingWitness
    target: BindingWitness


@dataclass(frozen=True, kw_only=True)
class SchemaObservation:
    """A checked meaning tied to the issued citations and original source roles."""

    id: str
    kind: Literal["concept", "relationship"]
    meaning: str
    source_role: str | None
    target_role: str | None
    modality: ObservationModality
    applicability: str
    qualifiers: tuple[str, ...]
    witnesses: tuple[BindingWitness, ...]
    record_binding: SchemaRecordBinding | None = None


@dataclass(frozen=True, kw_only=True)
class SchemaMappingHint:
    """A proposed correspondence with no effect on approved mappings."""

    definition: DefinitionId
    reference: ReferenceDefinitionId
    relation: MappingRelation
    reason: str


@dataclass(frozen=True, kw_only=True)
class SchemaReviewEvidence:
    """Scope and source witnesses shown next to one discovery review decision."""

    questions: tuple[CompetencyQuestion, ...]
    observations: tuple[SchemaObservation, ...]
    source_context: tuple[DiscoverySourceContext, ...]
    as_of: date | None
    rationale: str
