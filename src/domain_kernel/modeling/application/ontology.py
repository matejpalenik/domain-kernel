"""Ports for opt-in RDF syntax processing."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.ontology_assets import Iri, OntologySyntax
    from domain_kernel._shared.domain.ontology_documents import (
        OntologyCapabilities,
        OntologyDocument,
        OntologyLimits,
        ParsedOntology,
    )


@runtime_checkable
class OntologyAdapter(Protocol, metaclass=ABCMeta):
    """Parse and render asserted syntax using only supplied resources."""

    @property
    @abstractmethod
    def capabilities(self) -> OntologyCapabilities:
        """Declare the engine fingerprint and supported syntaxes."""

    @abstractmethod
    def parse(
        self,
        *,
        document: OntologyDocument,
        resources: Sequence[OntologyDocument],
        limits: OntologyLimits,
    ) -> ParsedOntology:
        """Materialize the complete original dataset under the supplied limits."""

    @abstractmethod
    def serialize(
        self,
        *,
        ontology: ParsedOntology,
        syntax: OntologySyntax,
        document_iri: Iri,
        limits: OntologyLimits,
    ) -> OntologyDocument:
        """Render the complete dataset in a supported target syntax."""
