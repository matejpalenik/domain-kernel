"""Explicit adoption of a complete immutable ontology module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class OntologyModuleDefinition:
    """Explicit adoption of a complete immutable ontology module."""

    ontology: OntologyClosure
    kind: Literal[DefinitionKind.ONTOLOGY_MODULE] = DefinitionKind.ONTOLOGY_MODULE

    def __post_init__(self) -> None:
        """Require the verified original ontology closure."""
        RuntimeTypeValidation.require_exact(
            value=self.ontology, expected=OntologyClosure, field="Adopted ontology"
        )
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=DefinitionKind, field="Definition kind"
        )
        if self.kind is not DefinitionKind.ONTOLOGY_MODULE:
            raise ValueError("Select the ontology-module body kind")
