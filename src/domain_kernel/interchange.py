"""Standalone projections of exact published bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from domain_kernel.modeling.application.json_schema_projection import JsonSchemaExporter
from domain_kernel.modeling.application.linkml_projection import assess_linkml
from domain_kernel.modeling.application.rdf_projection import RdfLibProjector
from domain_kernel.modeling.domain.interchange import (
    RDF_MAPPING,
    JsonSchemaProjectionRequest,
    LinkmlProjectionRequest,
    RdfProjectionRequest,
    RdfSyntax,
    require_projection_request,
)
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId

if TYPE_CHECKING:
    from domain_kernel._shared.domain.ontology_assets import Iri
    from domain_kernel.modeling.domain.interchange import (
        ProjectionAssessment,
        ProjectionRequest,
        SemanticProjection,
    )
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle


def assess_projection(
    *,
    bundle: DomainModelBundle,
    request: ProjectionRequest,
) -> ProjectionAssessment:
    """Explain mapping requirements for the exact requested projection."""
    require_projection_request(request=request)
    match request:
        case JsonSchemaProjectionRequest():
            return JsonSchemaExporter().assess(bundle=bundle, request=request)
        case RdfProjectionRequest():
            return RdfLibProjector().assess(bundle=bundle, request=request)
        case LinkmlProjectionRequest():
            return assess_linkml(bundle=bundle, request=request)
        case _:
            assert_never(request)


def project_semantics(
    *,
    bundle: DomainModelBundle,
    base_iri: Iri,
    syntax: RdfSyntax = RdfSyntax.TURTLE,
    mapping_version: str = RDF_MAPPING.value,
) -> SemanticProjection:
    """Project the exact published graph closure into separate RDF graph roles."""
    return RdfLibProjector().project(
        bundle=bundle,
        request=RdfProjectionRequest(
            base_iri=base_iri, syntax=syntax, mapping=MappingId(value=mapping_version)
        ),
    )
