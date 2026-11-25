"""Exact ontology root and its materialized closure digest."""

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class OntologyClosurePin:
    """Exact ontology root and its materialized closure digest."""

    root: OntologyDocumentPin
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Require an immutable document pin and exact digest."""
        RuntimeTypeValidation.require_exact(
            value=self.root, expected=OntologyDocumentPin, field="Ontology root"
        )
        RuntimeTypeValidation.require_exact(
            value=self.content_hash, expected=ContentHash, field="Ontology closure hash"
        )
