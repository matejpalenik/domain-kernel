"""Verify exact releases, analyze shared RDF coverage and render every graph role."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final, override

from domain_kernel._shared.application.artifacts import ExportPayload
from domain_kernel._shared.domain.artifacts import SemanticArtifactMetadata, SemanticGraphRole
from domain_kernel._shared.domain.ontology_documents import OntologyLimits
from domain_kernel._shared.domain.ontology_errors import (
    InvalidOntologyError,
    MissingDependencyError,
)
from domain_kernel._shared.domain.shape_graph import adopted_ontologies
from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.application.interchange import SemanticProjector
from domain_kernel.modeling.domain.dependencies import dependency_closure
from domain_kernel.modeling.domain.interchange import (
    RDF_MAPPING,
    RDF_VOCABULARY,
    MappingDescriptor,
    ProjectionAvailability,
    ProjectionBlockedError,
    ProjectionRemedy,
    RdfProjectionRequest,
    RdfSyntax,
    SemanticDocument,
    SemanticOntologyDependency,
    SemanticProjection,
)
from domain_kernel.modeling.domain.projection_analysis import make_assessment
from domain_kernel.modeling.domain.rdf_analysis import rdf_findings
from domain_kernel.modeling.domain.rdf_graphs import graph_iri, rdf_graphs
from domain_kernel.modeling.infrastructure.rdflib_adapter import RdfLibAdapter
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.errors import ResourceLimitError
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.validation import require_exact

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import ProjectionAssessment
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle


_LIMITATIONS = (
    "Published definitions and asserted axioms describe meanings and projected shapes.",
    "Instance shapes require separately populated business data.",
    "Processes, decisions and textual rules remain descriptive.",
    "Use the complete bundle for SDK interchange and exact review history.",
)


@dataclass(frozen=True, kw_only=True)
class _Analysis:
    assessment: ProjectionAssessment
    archives: tuple[DomainModelBundle, ...] = ()
    adapter: RdfLibAdapter | None = None


def _unavailable(
    *,
    bundle: DomainModelBundle,
    request: RdfProjectionRequest,
    availability: ProjectionAvailability,
    remedy: ProjectionRemedy,
    message: str,
) -> _Analysis:
    return _Analysis(
        assessment=make_assessment(
            model=bundle.model_version,
            request=request,
            availability=availability,
            issues=(Issue(code=availability.value, path=("mapping",), message=message),),
            remedies=(remedy,),
        )
    )


@final
class RdfLibProjector(SemanticProjector):
    """Use one graph analysis for read-only assessment and portable rendering."""

    def _analyze(self, *, bundle: DomainModelBundle, request: RdfProjectionRequest) -> _Analysis:
        require_valid_bundle(bundle=bundle)
        require_exact(value=request, expected=RdfProjectionRequest, field="RDF projection request")
        if request.mapping != RDF_MAPPING:
            return _unavailable(
                bundle=bundle,
                request=request,
                availability=ProjectionAvailability.UNSUPPORTED_MAPPING,
                remedy=ProjectionRemedy.SELECT_SUPPORTED_MAPPING,
                message="Select dk-rdf/1.0 for this RDF projection.",
            )
        try:
            adapter = RdfLibAdapter()
        except MissingDependencyError:
            return _unavailable(
                bundle=bundle,
                request=request,
                availability=ProjectionAvailability.MISSING_DEPENDENCY,
                remedy=ProjectionRemedy.INSTALL_OPTIONAL_DEPENDENCY,
                message="Install the SDK's ontology extra.",
            )
        archives = (
            bundle,
            *dependency_closure(
                scope=bundle.scope,
                bundles=bundle.publication.candidate.dependency_bundles,
            ),
        )
        mapping = MappingDescriptor(
            id=RDF_MAPPING,
            vocabulary_iri=RDF_VOCABULARY,
            supported_capabilities=("formal-assertions", "model-provenance", "shacl-core-subset"),
            adapter_versions=(
                (adapter.capabilities.adapter_id, adapter.capabilities.adapter_version),
            ),
        )
        return _Analysis(
            assessment=make_assessment(
                model=bundle.model_version,
                request=request,
                availability=ProjectionAvailability.AVAILABLE,
                mapping=mapping,
                findings=rdf_findings(bundles=archives),
            ),
            archives=archives,
            adapter=adapter,
        )

    @override
    def assess(
        self,
        *,
        bundle: DomainModelBundle,
        request: RdfProjectionRequest,
    ) -> ProjectionAssessment:
        """Assess the exact full closure before selecting any role."""
        return self._analyze(bundle=bundle, request=request).assessment

    @override
    def project(
        self,
        *,
        bundle: DomainModelBundle,
        request: RdfProjectionRequest,
    ) -> SemanticProjection:
        """Render all four roles for every verified source release."""
        result = self._analyze(bundle=bundle, request=request)
        if not result.assessment.exportable:
            raise ProjectionBlockedError(assessment=result.assessment)
        adapter, mapping = result.adapter, result.assessment.mapping
        if adapter is None or mapping is None:
            raise ValueError("Select one available RDF mapping and renderer")
        base = request.base_iri
        graph_sets = tuple(
            (archive, rdf_graphs(bundle=archive, archives=result.archives, base=base))
            for archive in result.archives
        )
        rows = tuple(
            (archive, role, graph)
            for archive, graphs in graph_sets
            for role, graph in graphs.documents
        )
        try:
            payloads = adapter.render(
                statements=tuple(graph for _, _, graph in rows),
                syntax=request.syntax,
                limits=OntologyLimits(),
            )
        except (InvalidOntologyError, ResourceLimitError, MissingDependencyError):
            failed = _unavailable(
                bundle=bundle,
                request=request,
                availability=ProjectionAvailability.FAILED,
                remedy=ProjectionRemedy.INSPECT_DIAGNOSTICS,
                message="Use the complete bundle or a projection within the RDF renderer's limits.",
            )
            raise ProjectionBlockedError(assessment=failed.assessment) from None
        documents = tuple(
            SemanticDocument(
                model=archive.model_version,
                role=role,
                graph_iri=graph_iri(base=base, model=archive.model_version, role=role),
                syntax=request.syntax,
                payload=payload,
                content_hash=hash_bytes(content=payload),
            )
            for (archive, role, _), payload in zip(rows, payloads, strict=True)
        )
        adopted = {
            archive.model_version: adopted_ontologies(
                bodies=(item.body for item in archive.content.definitions)
            )
            for archive in result.archives
        }
        original_resources = tuple(
            dict.fromkeys(
                (
                    *(value for values in adopted.values() for value in values),
                    *(
                        closure
                        for archive in result.archives
                        if archive.publication.reference_pack is not None
                        for closure in archive.publication.reference_pack.ontologies
                    ),
                )
            )
        )
        dependencies = tuple(
            SemanticOntologyDependency(model=model, ontology=value.pin)
            for model, values in adopted.items()
            for value in values
        )
        return SemanticProjection(
            model=bundle.model_version,
            base_iri=base,
            mapping=mapping,
            documents=documents,
            identities=tuple(
                identity for _, graphs in graph_sets for identity in graphs.identities
            ),
            dependencies=tuple(archive.model_version for archive in result.archives[1:]),
            issues=result.assessment.issues,
            limitations=_LIMITATIONS,
            consumer_obligations=result.assessment.consumer_obligations,
            ontologies=original_resources,
            ontology_dependencies=dependencies,
        )


def rdf_payload(
    *,
    bundle: DomainModelBundle,
    request: RdfProjectionRequest,
    role: SemanticGraphRole,
) -> ExportPayload:
    """Select the root document only after full semantic analysis and rendering."""
    projection = RdfLibProjector().project(bundle=bundle, request=request)
    document = next(
        item
        for item in projection.documents
        if item.model == bundle.model_version and item.role is role
    )
    ontology_pins = tuple(dict.fromkeys(item.ontology for item in projection.ontology_dependencies))
    return ExportPayload(
        media_type="text/turtle" if document.syntax is RdfSyntax.TURTLE else "application/ld+json",
        content_hash=document.content_hash,
        chunks=(document.payload,),
        projection_limits=projection.limitations,
        semantic=SemanticArtifactMetadata(
            model=bundle.model_version,
            graph_iri=document.graph_iri,
            role=role,
            mapping_version=projection.mapping.id.value,
            ontology_dependencies=ontology_pins,
        ),
        consumer_obligations=projection.consumer_obligations,
    )
