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
from domain_kernel.shared.validation import require_exact, snapshot_sequence

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
