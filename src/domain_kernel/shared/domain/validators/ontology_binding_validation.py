"""Validate typed ontology dependencies."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


class OntologyBindingValidation:
    """Check the typed pins and IRI shared by import and context bindings."""

    @staticmethod
    def require_binding(
        *, source: OntologyDocumentPin, iri: Iri, target: OntologyDocumentPin
    ) -> None:
        """Require exact types for the referring document, IRI and dependency document."""
        RuntimeTypeValidation.require_exact(
            value=source, expected=OntologyDocumentPin, field="Referring document"
        )
        RuntimeTypeValidation.require_exact(
            value=iri, expected=Iri, field="Resolved dependency IRI"
        )
        RuntimeTypeValidation.require_exact(
            value=target, expected=OntologyDocumentPin, field="Dependency document"
        )
