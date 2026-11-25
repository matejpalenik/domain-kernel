"""An inert typed RDF statement, with an optional named graph."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.rdf_literal import RdfLiteral
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class OntologyStatement:
    """An inert typed RDF statement, with an optional named graph."""

    subject: Iri | BlankNode
    predicate: Iri
    object: Iri | BlankNode | RdfLiteral
    graph: Iri | BlankNode | None = None

    def __post_init__(self) -> None:
        """Require the exact supported RDF term at each position."""
        if type(self.subject) not in (Iri, BlankNode):
            raise TypeError("Use an IRI or blank node as the subject")
        RuntimeTypeValidation.require_exact(
            value=self.predicate, expected=Iri, field="Statement predicate"
        )
        if type(self.object) not in (Iri, BlankNode, RdfLiteral):
            raise TypeError("Use an IRI, blank node or literal as the object")
        if self.graph is not None and type(self.graph) not in (Iri, BlankNode):
            raise TypeError("Use an IRI or blank node as the graph name")
