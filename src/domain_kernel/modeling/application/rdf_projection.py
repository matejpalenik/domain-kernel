"""Verify exact releases, analyze shared RDF coverage and render every graph role."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final, override
from urllib.parse import quote

from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.application.interchange import SemanticProjector
from domain_kernel.modeling.application.shacl_shapes import compile_shacl
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
    ValidationGraphs,
)
from domain_kernel.modeling.domain.projection_analysis import make_assessment
from domain_kernel.modeling.domain.rdf_analysis import rdf_findings
from domain_kernel.modeling.domain.rdf_graphs import (
    RdfModelGraphs,
    candidate_graphs,
    candidate_pin,
    graph_iri,
    model_iri,
    rdf_graphs,
)
from domain_kernel.modeling.domain.snapshot_integrity import candidate_digest
from domain_kernel.modeling.infrastructure.rdflib_adapter import RdfLibAdapter
from domain_kernel.shared.application.artifacts import ExportPayload
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.enums.semantic_graph_role import SemanticGraphRole
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.errors.missing_dependency_error import MissingDependencyError
from domain_kernel.shared.domain.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)
from domain_kernel.shared.domain.policies.shape_graph import adopted_ontologies
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_limits import OntologyLimits
from domain_kernel.shared.domain.value_objects.semantic_artifact_metadata import (
    SemanticArtifactMetadata,
)
from domain_kernel.shared.errors import ResourceLimitError, StaleStateError
from domain_kernel.shared.hashing import hash_bytes
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import ProjectionAssessment
    from domain_kernel.modeling.domain.snapshots import Candidate, DomainModelBundle
    from domain_kernel.reference_packs.api.packs import ReferencePack


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
    graph_sets: tuple[tuple[DomainModelBundle, RdfModelGraphs], ...] = ()


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


def _mapping(*, adapter: RdfLibAdapter) -> MappingDescriptor:
    return MappingDescriptor(
        id=RDF_MAPPING,
        vocabulary_iri=RDF_VOCABULARY,
        supported_capabilities=("formal-assertions", "model-provenance", "shacl-core-subset"),
        adapter_versions=((adapter.capabilities.adapter_id, adapter.capabilities.adapter_version),),
    )


def _archive_roles(
    *,
    archive: DomainModelBundle,
    archives: tuple[DomainModelBundle, ...],
    base: Iri,
) -> tuple[RdfModelGraphs, tuple[Issue, ...]]:
    graph_set = rdf_graphs(bundle=archive, archives=archives, base=base)
    intrinsic = dict(graph_set.documents)
    shapes = compile_shacl(
        definitions=archive.content.definitions,
        base=model_iri(base=base, model=archive.model_version),
        graphs=graph_set,
    )
    intrinsic[SemanticGraphRole.MODEL_SHAPES] = (
        *intrinsic[SemanticGraphRole.MODEL_SHAPES],
        *shapes.model,
    )
    intrinsic[SemanticGraphRole.INSTANCE_SHAPES] = (
        *intrinsic[SemanticGraphRole.INSTANCE_SHAPES],
        *shapes.instance,
    )
    return replace(graph_set, documents=tuple(intrinsic.items())), (
        *graph_set.issues,
        *shapes.issues,
    )


@final
class RdfLibProjector(SemanticProjector):
    """Use one graph analysis for read-only assessment and portable rendering."""

    def _analyze(self, *, bundle: DomainModelBundle, request: RdfProjectionRequest) -> _Analysis:
        require_valid_bundle(bundle=bundle)
        RuntimeTypeValidation.require_exact(
            value=request, expected=RdfProjectionRequest, field="RDF projection request"
        )
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
        mapped = tuple(
            (archive, *_archive_roles(archive=archive, archives=archives, base=request.base_iri))
            for archive in archives
        )
        return _Analysis(
            assessment=make_assessment(
                model=bundle.model_version,
                request=request,
                availability=ProjectionAvailability.AVAILABLE,
                mapping=_mapping(adapter=adapter),
                findings=rdf_findings(bundles=archives),
                issues=tuple(issue for _, _, issues in mapped for issue in issues),
            ),
            archives=archives,
            adapter=adapter,
            graph_sets=tuple((archive, graphs) for archive, graphs, _ in mapped),
        )

    @override
    def validation_graphs(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
        mapping_version: str,
    ) -> ValidationGraphs:
        if mapping_version != RDF_MAPPING.value:
            raise UnsupportedCapabilityError(message="Select dk-rdf/1.0 for candidate validation.")
        if candidate.content_hash != candidate_digest(
            candidate=candidate
        ) or candidate.reference_pack != (None if reference_pack is None else reference_pack.pin):
            raise StaleStateError(message="Use the exact candidate and selected reference pack.")
        base = Iri(
            value=(
                "https://domain-kernel.invalid/validation/"
                + quote(candidate.content_hash.value, safe="")
                + "/"
            )
        )
        archives = dependency_closure(scope=candidate.scope, bundles=candidate.dependency_bundles)
        intrinsic = candidate_graphs(candidate=candidate, archives=archives, base=base)
        roles = dict(intrinsic.documents)
        embedded = [
            dict(rdf_graphs(bundle=archive, archives=archives, base=base).documents)
            for archive in archives
        ]
        for role in (SemanticGraphRole.MODEL_METADATA, SemanticGraphRole.INSTANCE_SHAPES):
            roles[role] = tuple(
                dict.fromkeys(
                    (*roles[role], *(row for graph in embedded for row in graph[role])),
                )
            )
        authored = compile_shacl(
            definitions=candidate.content.definitions,
            base=base,
            graphs=replace(intrinsic, documents=tuple(roles.items())),
        )
        return ValidationGraphs(
            candidate=candidate_pin(candidate=candidate),
            mapping=_mapping(adapter=RdfLibAdapter()),
            model_metadata=roles[SemanticGraphRole.MODEL_METADATA],
            model_shapes=(*roles[SemanticGraphRole.MODEL_SHAPES], *authored.model),
            instance_shapes=(*roles[SemanticGraphRole.INSTANCE_SHAPES], *authored.instance),
            locations=(*intrinsic.locations, *authored.locations),
            issues=(*intrinsic.issues, *authored.issues),
            asserted_ontologies=(
                roles[SemanticGraphRole.ONTOLOGY],
                *(graph[SemanticGraphRole.ONTOLOGY] for graph in embedded),
            ),
            adopted_ontologies=adopted_ontologies(
                bodies=(
                    definition.body
                    for snapshot in (
                        candidate,
                        *(archive.publication.candidate for archive in archives),
                    )
                    for definition in snapshot.content.definitions
                )
            ),
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
        graph_sets = result.graph_sets
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
