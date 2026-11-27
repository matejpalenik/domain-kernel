"""Use one analysis for LinkML preflight, exact interchange and proposal import."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final, override

from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.application.errors.missing_dependency_error import (
    MissingDependencyError,
)
from domain_kernel.modeling.application.interchange import LinkmlMapper
from domain_kernel.modeling.domain.errors.invalid_schema_error import InvalidSchemaError
from domain_kernel.modeling.domain.errors.projection_blocked_error import ProjectionBlockedError
from domain_kernel.modeling.domain.interchange import (
    LINKML_MAPPING,
    LinkmlProjectionRequest,
    ProjectionAvailability,
    ProjectionFeature,
    ProjectionLocation,
    ProjectionRemedy,
)
from domain_kernel.modeling.domain.json_schema import json_findings
from domain_kernel.modeling.domain.linkml import (
    LinkmlProjection,
    SchemaDocument,
)
from domain_kernel.modeling.domain.linkml_render import render_linkml, schema_iri
from domain_kernel.modeling.domain.models import ModelInfo
from domain_kernel.modeling.domain.projection_analysis import (
    blocked_feature,
    host_feature,
    make_assessment,
)
from domain_kernel.modeling.domain.schema_selection import PublishedShapes
from domain_kernel.modeling.infrastructure.linkml_closure import verify_closure
from domain_kernel.modeling.infrastructure.linkml_documents import (
    adapter_mapping,
    encode,
    packaged_types,
)
from domain_kernel.modeling.infrastructure.linkml_import import import_shapes
from domain_kernel.reconciliation.domain.identifiers.mapping_id import MappingId
from domain_kernel.shared.diagnostics.issue import Issue
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.nullability import Nullability
from domain_kernel.shared.domain.value_objects.collection_semantics_obligation import (
    CollectionSemanticsObligation,
)
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
    from domain_kernel.modeling.domain.interchange import (
        LinkmlSyntax,
        ProjectionAssessment,
        ProjectionFinding,
    )
    from domain_kernel.modeling.domain.linkml import SchemaImportResult
    from domain_kernel.modeling.domain.schema_selection import SelectedDefinition
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.shared.domain.value_objects.iri import Iri

_SUPPORTED = (
    ConceptDefinition,
    StructuredValueDefinition,
    ValueSetDefinition,
    UnitDefinition,
    RelationshipDefinition,
)


def _findings(*, shapes: Sequence[SelectedDefinition]) -> tuple[ProjectionFinding, ...]:
    shared = json_findings(selected=shapes)
    findings = [
        item
        for item in shared
        if item.feature
        not in {
            ProjectionFeature.VALUE_EQUALITY,
            ProjectionFeature.FIELD_PRESENCE,
            ProjectionFeature.ITEM_BOUNDS,
            ProjectionFeature.NULLABILITY,
        }
    ]
    for item in shapes:
        body = item.definition.body
        if not isinstance(body, _SUPPORTED):
            findings.append(
                blocked_feature(
                    location=ProjectionLocation(definition=item.pin),
                    feature=ProjectionFeature.DEFINITION,
                    message="Select the complete bundle or a subset of portable shapes.",
                )
            )
        if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
            findings.extend(_fields(item=item, body=body))
    return tuple(findings)


def _fields(
    *, item: SelectedDefinition, body: ConceptDefinition | StructuredValueDefinition
) -> tuple[ProjectionFinding, ...]:
    findings: list[ProjectionFinding] = []
    for field in body.attributes:
        location = ProjectionLocation(definition=item.pin, member=field.id)
        if field.nullability is Nullability.ALLOWED:
            findings.append(
                blocked_feature(
                    location=location,
                    feature=ProjectionFeature.NULLABILITY,
                    message="Use JSON Schema or the complete bundle for present null values.",
                )
            )
        if field.collection is CollectionKind.LIST:
            findings.append(
                blocked_feature(
                    location=location,
                    feature=ProjectionFeature.COLLECTION_KIND,
                    message="Use JSON Schema or the complete bundle for ordered repeated values.",
                )
            )
        if field.constraints:
            findings.append(
                blocked_feature(
                    location=location,
                    feature=ProjectionFeature.CONSTRAINT,
                    message="Use the complete bundle to preserve authored field constraints.",
                )
            )
        if field.collection is CollectionKind.SET:
            findings.append(
                host_feature(
                    location=location,
                    feature=ProjectionFeature.COLLECTION_KIND,
                    message="Check presence, bounds and typed uniqueness before normalization.",
                    obligation=CollectionSemanticsObligation(owner=item.pin, attribute=field.id),
                )
            )
    return tuple(findings)


def _unavailable(
    *,
    bundle: DomainModelBundle,
    request: LinkmlProjectionRequest,
    availability: ProjectionAvailability,
    remedy: ProjectionRemedy,
    message: str,
) -> ProjectionAssessment:
    return make_assessment(
        model=bundle.model_version,
        request=request,
        availability=availability,
        issues=(Issue(code=availability.value, path=("mapping",), message=message),),
        remedies=(remedy,),
    )


@dataclass(frozen=True, kw_only=True)
class _Analysis:
    assessment: ProjectionAssessment
    projection: LinkmlProjection | None = None


@final
class LinkmlSchemaMapper(LinkmlMapper):
    """Map only finite flat shapes and hash-verified supplied schema dependencies."""

    @override
    def assess(
        self, *, bundle: DomainModelBundle, request: LinkmlProjectionRequest
    ) -> ProjectionAssessment:
        """Explain support and obligations for the actual schema that would be emitted."""
        return self._analyze(bundle=bundle, request=request).assessment

    @override
    def project(
        self,
        *,
        bundle: DomainModelBundle,
        base_iri: Iri,
        definition_ids: Sequence[DefinitionId] | None,
        syntax: LinkmlSyntax,
        mapping_version: str,
    ) -> LinkmlProjection:
        """Build the exact analyzed standalone schema and its selection manifest."""
        request = LinkmlProjectionRequest(
            base_iri=base_iri,
            definition_ids=definition_ids,
            syntax=syntax,
            mapping=MappingId(value=mapping_version),
        )
        result = self._analyze(bundle=bundle, request=request)
        if result.projection is None:
            if result.assessment.availability is ProjectionAvailability.MISSING_DEPENDENCY:
                raise MissingDependencyError(message="Install the SDK's linkml extra.")
            raise ProjectionBlockedError(assessment=result.assessment)
        return result.projection

    def _analyze(self, *, bundle: DomainModelBundle, request: LinkmlProjectionRequest) -> _Analysis:
        require_valid_bundle(bundle=bundle)
        index = PublishedShapes(bundle=bundle)
        roots = index.local_selection(definition_ids=request.definition_ids)
        if request.mapping != LINKML_MAPPING:
            return _Analysis(
                assessment=_unavailable(
                    bundle=bundle,
                    request=request,
                    availability=ProjectionAvailability.UNSUPPORTED_MAPPING,
                    remedy=ProjectionRemedy.SELECT_SUPPORTED_MAPPING,
                    message="Select the dk-linkml/1.0 mapping.",
                )
            )
        try:
            mapping = adapter_mapping()
            _ = packaged_types()
        except MissingDependencyError:
            return _Analysis(
                assessment=_unavailable(
                    bundle=bundle,
                    request=request,
                    availability=ProjectionAvailability.MISSING_DEPENDENCY,
                    remedy=ProjectionRemedy.INSTALL_OPTIONAL_DEPENDENCY,
                    message="Install the SDK's linkml extra.",
                )
            )
        except InvalidSchemaError:
            return _Analysis(
                assessment=_unavailable(
                    bundle=bundle,
                    request=request,
                    availability=ProjectionAvailability.FAILED,
                    remedy=ProjectionRemedy.INSPECT_DIAGNOSTICS,
                    message="Restore the registered packaged LinkML types.",
                )
            )
        try:
            closure = index.closure(roots=roots, include_model_semantics=True)
            report = make_assessment(
                model=bundle.model_version,
                request=request,
                availability=ProjectionAvailability.AVAILABLE,
                mapping=mapping,
                findings=_findings(shapes=closure),
            )
            if not report.exportable:
                return _Analysis(assessment=report)
            selected = tuple(item.pin for item in closure)
            active = index.local_selection(definition_ids=None)
            excluded = tuple(
                item.pin.definition_id for item in active if item.pin not in set(selected)
            )
            raw, identities = render_linkml(
                index=index,
                selected=closure,
                excluded=excluded,
                base=request.base_iri,
                report=report,
            )
            payload = encode(raw=raw, syntax=request.syntax)
        except (ValueError, TypeError, ResourceLimitError, RecursionError):
            return _Analysis(
                assessment=_unavailable(
                    bundle=bundle,
                    request=request,
                    availability=ProjectionAvailability.FAILED,
                    remedy=ProjectionRemedy.INSPECT_DIAGNOSTICS,
                    message="Inspect the bounded shape selection.",
                )
            )
        return _Analysis(
            assessment=report,
            projection=LinkmlProjection(
                model=bundle.model_version,
                mapping=mapping,
                schema=SchemaDocument(
                    schema_iri=schema_iri(base=request.base_iri, model=bundle.model_version),
                    syntax=request.syntax,
                    payload=payload,
                    content_hash=Hashing.hash_bytes(content=payload),
                ),
                dependencies=(),
                selected=selected,
                excluded_definition_ids=excluded,
                identities=identities,
                issues=report.issues,
                consumer_obligations=report.consumer_obligations,
            ),
        )

    @override
    def load(
        self,
        *,
        document: SchemaDocument,
        dependencies: Sequence[SchemaDocument],
        model_info: ModelInfo,
        reason: str,
        mapping_version: str,
        max_bytes: int,
    ) -> SchemaImportResult:
        """Check document integrity, then map fresh IDs against the inspected destination."""
        RuntimeTypeValidation.require_exact(
            value=document, expected=SchemaDocument, field="Schema document"
        )
        RuntimeTypeValidation.require_exact(
            value=model_info, expected=ModelInfo, field="Receiving workspace snapshot"
        )
        RuntimeTypeValidation.require_exact(
            value=max_bytes, expected=int, field="Schema byte limit"
        )
        TextValidation.require_text(value=reason, field="Import reason")
        TextValidation.require_text(value=mapping_version, field="LinkML mapping version")
        if max_bytes < 1:
            raise ValueError("Set a positive byte limit")
        if mapping_version != LINKML_MAPPING.value:
            raise UnsupportedCapabilityError(message="Select the dk-linkml/1.0 mapping.")
        supplied = SequenceValidation.snapshot_sequence(
            items=dependencies, item_type=SchemaDocument, field="Schema imports"
        )
        mapping = adapter_mapping()
        closure = verify_closure(document=document, dependencies=supplied, max_bytes=max_bytes)
        return import_shapes(closure=closure, model_info=model_info, reason=reason, mapping=mapping)


def assess_linkml(
    *, bundle: DomainModelBundle, request: LinkmlProjectionRequest
) -> ProjectionAssessment:
    """Dispatch through the same pure analyzer as LinkML projection."""
    return LinkmlSchemaMapper().assess(bundle=bundle, request=request)
