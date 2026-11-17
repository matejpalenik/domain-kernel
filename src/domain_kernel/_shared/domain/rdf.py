"""Typed RDF records shared by supplied graph evidence and ontology interchange."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel._shared.domain.model_values import LanguageTag
from domain_kernel._shared.domain.ontology_assets import BlankNode, Iri
from domain_kernel.shared.validation import require_exact


@dataclass(frozen=True, kw_only=True)
class RdfLiteral:
    """An exact RDF literal with optional datatype or language."""

    value: str
    datatype: Iri | None = None
    language: str | None = None
    kind: Literal["literal"] = "literal"

    def __post_init__(self) -> None:
        """Retain lexical values and canonicalize a well-formed language tag."""
        require_exact(value=self.value, expected=str, field="Literal value")
        require_exact(value=self.kind, expected=str, field="Literal kind")
        if self.kind != "literal":
            raise ValueError("Use the RDF literal discriminator")
        if self.datatype is not None:
            require_exact(value=self.datatype, expected=Iri, field="Literal datatype")
        if self.language is not None:
            if self.datatype is not None:
                raise ValueError("Choose a datatyped or language-tagged literal")
            object.__setattr__(self, "language", LanguageTag(value=self.language).value)


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
        require_exact(value=self.predicate, expected=Iri, field="Statement predicate")
        if type(self.object) not in (Iri, BlankNode, RdfLiteral):
            raise TypeError("Use an IRI, blank node or literal as the object")
        if self.graph is not None and type(self.graph) not in (Iri, BlankNode):
            raise TypeError("Use an IRI or blank node as the graph name")


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


def statement_key(*, statement: OntologyStatement) -> tuple[tuple[str, ...], ...]:
    """Retain dataset placement and RDF term identity in canonical order."""
    return (
        node_value(node=statement.graph),
        node_value(node=statement.subject),
        node_value(node=statement.predicate),
        node_value(node=statement.object),
    )
