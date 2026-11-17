"""Standalone projections of exact published bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.modeling.application.rdf_projection import RdfLibProjector
from domain_kernel.modeling.domain.interchange import RDF_MAPPING, RdfProjectionRequest, RdfSyntax
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId

if TYPE_CHECKING:
    from domain_kernel._shared.domain.ontology_assets import Iri
    from domain_kernel.modeling.domain.interchange import ProjectionAssessment, SemanticProjection
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle


def assess_projection(
    *,
    bundle: DomainModelBundle,
    request: RdfProjectionRequest,
) -> ProjectionAssessment:
    """Explain mapping requirements for the exact requested projection."""
    return RdfLibProjector().assess(bundle=bundle, request=request)


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
