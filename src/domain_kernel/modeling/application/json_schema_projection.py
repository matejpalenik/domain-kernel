"""Run the same exact analysis for read-only JSON Schema preflight and delivery."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.application.contracts.export_payload import ExportPayload
from domain_kernel.modeling.domain.errors.projection_blocked_error import ProjectionBlockedError
from domain_kernel.modeling.domain.interchange import (
    JSON_SCHEMA_MAPPING,
    ProjectionAvailability,
    ProjectionRemedy,
)
from domain_kernel.modeling.domain.json_schema import (
    MAPPING,
    json_findings,
    schema_document,
    schema_iri,
)
from domain_kernel.modeling.domain.projection_analysis import make_assessment
from domain_kernel.modeling.domain.schema_selection import PublishedShapes
from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.value_objects.schema_artifact_metadata import (
    SchemaArtifactMetadata,
)
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import (
        JsonSchemaProjectionRequest,
        ProjectionAssessment,
    )
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle


@dataclass(frozen=True, kw_only=True)
class _Analysis:
    assessment: ProjectionAssessment
    payload: ExportPayload | None = None


@final
class JsonSchemaExporter:
    """Assess a selected root and deliver the schema from those same inputs."""

    def assess(
        self, *, bundle: DomainModelBundle, request: JsonSchemaProjectionRequest
    ) -> ProjectionAssessment:
        """Explain support and obligations without opening an artifact store."""
        return self._analyze(bundle=bundle, request=request).assessment

    def export(
        self, *, bundle: DomainModelBundle, request: JsonSchemaProjectionRequest
    ) -> ExportPayload:
        """Produce bytes only after running the same complete analysis."""
        result = self._analyze(bundle=bundle, request=request)
        if result.payload is None:
            raise ProjectionBlockedError(assessment=result.assessment)
        return result.payload

    def _analyze(
        self, *, bundle: DomainModelBundle, request: JsonSchemaProjectionRequest
    ) -> _Analysis:
        require_valid_bundle(bundle=bundle)
        index = PublishedShapes(bundle=bundle)
        root = index.root(request=request)
        normalized = replace(request, root=root.pin)
        try:
            selected = index.closure(roots=(root,), include_model_semantics=True)
            report = make_assessment(
                model=bundle.model_version,
                request=normalized,
                availability=ProjectionAvailability.AVAILABLE,
                mapping=MAPPING,
                findings=json_findings(selected=selected),
            )
            if not report.exportable:
                return _Analysis(assessment=report)
            content = CanonicalJson.encode(
                value=schema_document(
                    index=index,
                    root=root,
                    selected=selected,
                    base=request.base_iri,
                    report=report,
                )
            )
        except (ValueError, TypeError, ResourceLimitError, RecursionError):
            return _Analysis(
                assessment=make_assessment(
                    model=bundle.model_version,
                    request=normalized,
                    availability=ProjectionAvailability.FAILED,
                    mapping=MAPPING,
                    issues=(
                        Issue(
                            code="schema_analysis_failed",
                            path=("root",),
                            message="Inspect the selected shape or choose a smaller projection.",
                        ),
                    ),
                    remedies=(ProjectionRemedy.INSPECT_DIAGNOSTICS,),
                )
            )
        return _Analysis(
            assessment=report,
            payload=ExportPayload(
                media_type="application/schema+json",
                content_hash=Hashing.hash_bytes(content=content),
                chunks=(content,),
                consumer_obligations=report.consumer_obligations,
                schema=SchemaArtifactMetadata(
                    model=bundle.model_version,
                    document_iri=schema_iri(base=request.base_iri, owner=root.pin),
                    mapping_version=JSON_SCHEMA_MAPPING.value,
                    root=root.pin,
                ),
            ),
        )
