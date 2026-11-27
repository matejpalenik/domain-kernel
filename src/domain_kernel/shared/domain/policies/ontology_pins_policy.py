"""Order pins by their exact original identity, including the selected graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel.shared.domain.policies.rdf_order_policy import RdfOrderPolicy

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.iri import Iri
    from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin


@final
class OntologyPinsPolicy:
    """Index equivalent pin identifiers and order reviewed ontology documents."""

    @staticmethod
    def pin_key(*, pin: OntologyDocumentPin) -> tuple[str, ...]:
        """Order pins by their exact original identity, including the selected graph."""
        return (
            pin.document_iri.value,
            pin.content_hash.value,
            pin.ontology_iri.value if pin.ontology_iri is not None else "",
            pin.version_iri.value if pin.version_iri is not None else "",
            *RdfOrderPolicy.node_value(node=pin.ontology_graph),
        )

    @staticmethod
    def aliases(*, pin: OntologyDocumentPin) -> frozenset[Iri]:
        """Return exact admissible spellings for a requested ontology dependency."""
        return frozenset(
            value
            for value in (pin.document_iri, pin.ontology_iri, pin.version_iri)
            if value is not None
        )
