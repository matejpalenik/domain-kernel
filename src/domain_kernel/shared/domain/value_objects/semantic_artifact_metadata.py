"""Identify a projected graph and the exact dependencies used to render it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.enums.semantic_graph_role import SemanticGraphRole
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion
from domain_kernel.shared.domain.value_objects.ontology_closure_pin import OntologyClosurePin
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


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
