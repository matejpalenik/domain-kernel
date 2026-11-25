"""A pinned document's full asserted dataset and selected declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.policies.ontology_declarations import declaration_inventory
from domain_kernel.shared.domain.policies.rdf_order import statement_key
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_document import OntologyDocument
from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class ParsedOntology:
    """A pinned document's full asserted dataset and selected declarations."""

    document: OntologyDocument
    parser_id: str
    parser_version: str
    statements: Sequence[OntologyStatement] = field(repr=False)
    terms: Sequence[OntologyTermReference]
    import_iris: Sequence[Iri] = ()
    context_iris: Sequence[Iri] = ()

    def __post_init__(self) -> None:
        """Freeze statements and verify declared term and import inventories."""
        RuntimeTypeValidation.require_exact(
            value=self.document, expected=OntologyDocument, field="Parsed document"
        )
        TextValidation.require_text(value=self.parser_id, field="Ontology parser ID")
        TextValidation.require_text(value=self.parser_version, field="Ontology parser version")
        statements = SequenceValidation.snapshot_sequence(
            items=self.statements,
            item_type=OntologyStatement,
            field="Ontology statements",
        )
        statements = tuple(sorted(set(statements), key=lambda item: statement_key(statement=item)))
        object.__setattr__(self, "statements", statements)
        terms = SequenceValidation.snapshot_sequence(
            items=self.terms,
            item_type=OntologyTermReference,
            field="Declared ontology terms",
        )
        imports = SequenceValidation.snapshot_sequence(
            items=self.import_iris, item_type=Iri, field="Ontology imports"
        )
        if (terms, imports) != declaration_inventory(pin=self.document.pin, statements=statements):
            raise InvalidOntologyError(
                message="Match term and import inventories to the selected graph."
            )
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "import_iris", imports)
        contexts = SequenceValidation.snapshot_sequence(
            items=self.context_iris, item_type=Iri, field="JSON-LD contexts"
        )
        if tuple(sorted(set(contexts), key=lambda value: value.value)) != contexts:
            raise InvalidOntologyError(message="Supply each used context once in IRI order.")
        object.__setattr__(self, "context_iris", contexts)
