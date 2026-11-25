"""Ports for opt-in RDF syntax processing."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.semantics import (
        OntologyModuleResult,
        ReasoningRequest,
        ReasoningResult,
    )
    from domain_kernel.shared.domain.enums.module_extraction_method import ModuleExtractionMethod
    from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
    from domain_kernel.shared.domain.enums.reasoning_profile import ReasoningProfile
    from domain_kernel.shared.domain.enums.semantic_regime import SemanticRegime
    from domain_kernel.shared.domain.value_objects.iri import Iri
    from domain_kernel.shared.domain.value_objects.ontology_capabilities import OntologyCapabilities
    from domain_kernel.shared.domain.value_objects.ontology_closure import OntologyClosure
    from domain_kernel.shared.domain.value_objects.ontology_document import OntologyDocument
    from domain_kernel.shared.domain.value_objects.ontology_limits import OntologyLimits
    from domain_kernel.shared.domain.value_objects.ontology_term_reference import (
        OntologyTermReference,
    )
    from domain_kernel.shared.domain.value_objects.parsed_ontology import ParsedOntology


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


@runtime_checkable
class OntologyReasoner(Protocol, metaclass=ABCMeta):
    """Host reasoning capability over verified, already materialized ontology inputs."""

    @property
    @abstractmethod
    def capabilities(self) -> OntologyCapabilities:
        """Report the exact engine and supported reasoning combinations."""

    @abstractmethod
    async def reason(
        self, *, ontology: OntologyClosure, request: ReasoningRequest, limits: OntologyLimits
    ) -> ReasoningResult:
        """Answer within the budgets and stop external work on cancellation."""


@runtime_checkable
class OntologyModuleExtractor(Protocol, metaclass=ABCMeta):
    """Host capability for formal extraction from verified, materialized input."""

    @property
    @abstractmethod
    def capabilities(self) -> OntologyCapabilities:
        """Report the exact engine, methods and supported semantic guarantees."""

    @abstractmethod
    async def extract(  # noqa: PLR0913 -- exact request fields cross the host boundary
        self,
        *,
        ontology: OntologyClosure,
        seeds: Sequence[OntologyTermReference],
        method: ModuleExtractionMethod,
        profile: ReasoningProfile,
        regime: SemanticRegime,
        ontology_iri: Iri,
        limits: OntologyLimits,
    ) -> OntologyModuleResult:
        """Produce a bounded derived module and stop external work on cancellation."""
