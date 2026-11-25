"""A JSON-LD context consulted during one document's parse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.validators.ontology_binding_validation import (
    OntologyBindingValidation,
)

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.iri import Iri
    from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin


@dataclass(frozen=True, kw_only=True)
class OntologyContextBinding:
    """A JSON-LD context consulted during one document's parse."""

    source: OntologyDocumentPin
    context_iri: Iri
    target: OntologyDocumentPin

    def __post_init__(self) -> None:
        """Require typed referring and context document identities."""
        OntologyBindingValidation.require_binding(
            source=self.source, iri=self.context_iri, target=self.target
        )
