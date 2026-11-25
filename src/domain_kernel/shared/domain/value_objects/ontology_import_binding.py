"""An OWL import resolved to an exact supplied document."""

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
class OntologyImportBinding:
    """An OWL import resolved to an exact supplied document."""

    source: OntologyDocumentPin
    import_iri: Iri
    target: OntologyDocumentPin

    def __post_init__(self) -> None:
        """Require typed referring and imported document identities."""
        OntologyBindingValidation.require_binding(
            source=self.source, iri=self.import_iri, target=self.target
        )
