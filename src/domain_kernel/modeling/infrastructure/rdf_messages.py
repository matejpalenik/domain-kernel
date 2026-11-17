"""Typed messages for the optional RDF parser process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

# Runtime imports support reflected closed-wire field resolution.
from domain_kernel._shared.domain.ontology_assets import Iri, OntologySyntax
from domain_kernel._shared.domain.ontology_documents import (
    OntologyDocument,
    OntologyLimits,
    ParsedOntology,
)
from domain_kernel._shared.domain.rdf import OntologyStatement
from domain_kernel.modeling.domain.interchange import RdfSyntax
from domain_kernel.shared.validation import is_non_string_sequence, require_exact, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class ParseRdf:
    """Original document and the only eligible JSON-LD resources."""

    document: OntologyDocument
    resources: Sequence[OntologyDocument]
    limits: OntologyLimits

    def __post_init__(self) -> None:
        """Detach supplied context resources before passing them to the parser."""
        require_exact(value=self.document, expected=OntologyDocument, field="RDF original")
        require_exact(value=self.limits, expected=OntologyLimits, field="RDF limits")
        object.__setattr__(
            self,
            "resources",
            snapshot_sequence(
                items=self.resources,
                item_type=OntologyDocument,
                field="RDF context originals",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class WriteRdf:
    """An exact asserted dataset and the desired output representation."""

    ontology: ParsedOntology
    syntax: OntologySyntax
    document_iri: Iri
    limits: OntologyLimits

    def __post_init__(self) -> None:
        """Require a complete typed serialization command."""
        require_exact(value=self.ontology, expected=ParsedOntology, field="RDF dataset")
        require_exact(value=self.syntax, expected=OntologySyntax, field="RDF serialization syntax")
        require_exact(value=self.document_iri, expected=Iri, field="RDF output IRI")
        require_exact(value=self.limits, expected=OntologyLimits, field="RDF limits")


@dataclass(frozen=True, kw_only=True)
class RenderRdfGraphs:
    """Render validated graph documents with one selected syntax and resource budget."""

    statements: Sequence[Sequence[OntologyStatement]]
    syntax: RdfSyntax
    limits: OntologyLimits

    def __post_init__(self) -> None:
        """Detach the supplied standalone graph documents."""
        if not is_non_string_sequence(self.statements):
            raise TypeError("Supply a sequence of RDF graphs")
        graphs = tuple(
            snapshot_sequence(items=graph, item_type=OntologyStatement, field="RDF statements")
            for graph in self.statements
        )
        if any(row.graph is not None for graph in graphs for row in graph):
            raise ValueError("Select graph placement separately from the standalone documents")
        object.__setattr__(self, "statements", graphs)
        require_exact(value=self.syntax, expected=RdfSyntax, field="RDF graph syntax")
        require_exact(value=self.limits, expected=OntologyLimits, field="RDF rendering limits")


@dataclass(frozen=True, kw_only=True)
class RenderedRdfGraphs:
    """Bounded graph byte outputs from the RDF worker."""

    payloads: Sequence[bytes]

    def __post_init__(self) -> None:
        """Validate the exact independent output documents."""
        object.__setattr__(
            self,
            "payloads",
            snapshot_sequence(
                items=self.payloads,
                item_type=bytes,
                field="RDF graph bytes",
            ),
        )
