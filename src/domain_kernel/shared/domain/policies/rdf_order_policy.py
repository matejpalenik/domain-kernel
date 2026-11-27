"""Preserve all RDF term kinds and their lexical spelling."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.rdf_literal import RdfLiteral

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement


@final
class RdfOrderPolicy:
    """Define stable ordering for RDF terms and statements."""

    @staticmethod
    def node_value(*, node: Iri | BlankNode | RdfLiteral | None) -> tuple[str, ...]:
        """Preserve all RDF term kinds and their lexical spelling."""
        if isinstance(node, Iri):
            return ("iri", node.value)
        if isinstance(node, BlankNode):
            return ("blank", node.id)
        if isinstance(node, RdfLiteral):
            return (
                "literal",
                node.value,
                node.datatype.value if node.datatype is not None else "",
                node.language or "",
            )

        return ()

    @staticmethod
    def statement_key(*, statement: OntologyStatement) -> tuple[tuple[str, ...], ...]:
        """Retain dataset placement and RDF term identity in canonical order."""
        return (
            RdfOrderPolicy.node_value(node=statement.graph),
            RdfOrderPolicy.node_value(node=statement.subject),
            RdfOrderPolicy.node_value(node=statement.predicate),
            RdfOrderPolicy.node_value(node=statement.object),
        )
