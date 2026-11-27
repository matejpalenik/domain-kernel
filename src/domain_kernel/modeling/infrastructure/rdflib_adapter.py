"""Run RDFLib in a bounded child process with no implicit resource access."""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, final, override

from domain_kernel.modeling.application.errors.missing_dependency_error import (
    MissingDependencyError,
)
from domain_kernel.modeling.application.ontology import OntologyAdapter
from domain_kernel.modeling.infrastructure.rdf_messages import (
    CheckShacl,
    ParseRdf,
    RenderedRdfGraphs,
    RenderRdfGraphs,
    ShaclResults,
    WriteRdf,
)
from domain_kernel.shared.domain.codecs.record_codec import RecordCodec
from domain_kernel.shared.domain.enums.ontology_syntax import OntologySyntax
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.value_objects.ontology_capabilities import OntologyCapabilities
from domain_kernel.shared.domain.value_objects.ontology_document import OntologyDocument
from domain_kernel.shared.domain.value_objects.parsed_ontology import ParsedOntology
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.interchange import RdfSyntax
    from domain_kernel.shared.domain.value_objects.iri import Iri
    from domain_kernel.shared.domain.value_objects.ontology_limits import OntologyLimits
    from domain_kernel.shared.domain.value_objects.ontology_statement import OntologyStatement

RDFLIB_FORMATS = {
    OntologySyntax.TURTLE: "turtle",
    OntologySyntax.RDFXML: "xml",
    OntologySyntax.JSONLD: "json-ld",
    OntologySyntax.NTRIPLES: "nt",
    OntologySyntax.TRIG: "trig",
    OntologySyntax.NQUADS: "nquads",
}


def _invoke[T](
    *, message: ParseRdf | WriteRdf | RenderRdfGraphs | CheckShacl, expected: type[T]
) -> T:
    action = {
        ParseRdf: "parse",
        WriteRdf: "serialize",
        RenderRdfGraphs: "render",
        CheckShacl: "shacl",
    }[type(message)]
    try:
        result = subprocess.run(  # noqa: S603 - Fixed interpreter/module and typed stdin.
            [
                sys.executable,
                "-I",
                "-m",
                "domain_kernel.modeling.infrastructure.rdflib_worker",
                action,
            ],
            input=RecordCodec.encode(value=message, root_type=type(message)),
            capture_output=True,
            check=False,
            timeout=message.limits.timeout_ms / 1000,
        )
    except subprocess.TimeoutExpired:
        raise ResourceLimitError(message="Use an ontology within the parser time budget.") from None
    except OSError:
        raise MissingDependencyError(
            message="Enable the SDK's local ontology parser process."
        ) from None
    match result.returncode:
        case 0:
            return RecordCodec.decode(content=result.stdout, expected=expected, root_type=expected)
        case 3:
            raise ResourceLimitError(
                message="Use a dataset within the RDF parser's resource budget."
            )
        case 4:
            raise UnsupportedCapabilityError
        case _:
            raise InvalidOntologyError


@final
class RdfLibAdapter(OntologyAdapter):
    """Expose the RDFLib syntaxes that preserve supported RDF datasets."""

    def __init__(self) -> None:
        """Discover the optional distribution without importing it into the caller."""
        try:
            parser_version = version(distribution_name="rdflib")
        except PackageNotFoundError:
            raise MissingDependencyError from None
        self._capabilities = OntologyCapabilities(
            adapter_id="rdflib",
            adapter_version=parser_version,
            parse_syntaxes=tuple(RDFLIB_FORMATS),
            serialize_syntaxes=tuple(RDFLIB_FORMATS),
        )

    @property
    @override
    def capabilities(self) -> OntologyCapabilities:
        return self._capabilities

    @override
    def parse(
        self,
        *,
        document: OntologyDocument,
        resources: Sequence[OntologyDocument],
        limits: OntologyLimits,
    ) -> ParsedOntology:
        selected = (
            tuple(x for x in resources if x.syntax is OntologySyntax.JSONLD)
            if document.syntax is OntologySyntax.JSONLD
            else ()
        )
        return _invoke(
            message=ParseRdf(document=document, resources=selected, limits=limits),
            expected=ParsedOntology,
        )

    @override
    def serialize(
        self,
        *,
        ontology: ParsedOntology,
        syntax: OntologySyntax,
        document_iri: Iri,
        limits: OntologyLimits,
    ) -> OntologyDocument:
        return _invoke(
            message=WriteRdf(
                ontology=ontology, syntax=syntax, document_iri=document_iri, limits=limits
            ),
            expected=OntologyDocument,
        )

    def render(
        self,
        *,
        statements: Sequence[Sequence[OntologyStatement]],
        syntax: RdfSyntax,
        limits: OntologyLimits,
    ) -> tuple[bytes, ...]:
        """Render a complete collection of standalone graph documents."""
        result = _invoke(
            message=RenderRdfGraphs(statements=statements, syntax=syntax, limits=limits),
            expected=RenderedRdfGraphs,
        )
        return tuple(result.payloads)

    def validate_shacl(self, *, command: CheckShacl) -> ShaclResults:
        """Run the controlled metadata checker and separate shape syntax checks."""
        return _invoke(message=command, expected=ShaclResults)
