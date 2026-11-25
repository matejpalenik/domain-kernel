"""Original serialization and its exact declared identity."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.value_objects.ontology_document_pin import OntologyDocumentPin
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class OntologyDocument:
    """Original serialization and its exact declared identity."""

    pin: OntologyDocumentPin
    syntax: OntologySyntax
    payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        """Require exact original bytes and immutable declared identity."""
        RuntimeTypeValidation.require_exact(
            value=self.pin, expected=OntologyDocumentPin, field="Ontology document pin"
        )
        RuntimeTypeValidation.require_exact(
            value=self.syntax, expected=OntologySyntax, field="Ontology syntax"
        )
        RuntimeTypeValidation.require_exact(
            value=self.payload, expected=bytes, field="Ontology bytes"
        )
        if self.pin.content_hash != hash_bytes(content=self.payload):
            raise InvalidOntologyError(message="Restore the original ontology bytes for this pin.")
