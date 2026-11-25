"""Controlled pySHACL application adapter and diagnostic mapping."""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel.discovery.domain.identifiers.validation_report_id import ValidationReportId
from domain_kernel.modeling.application.rdf_projection import RdfLibProjector
from domain_kernel.modeling.application.shacl_shapes import SHACL_CORE_PREDICATES
from domain_kernel.modeling.application.validation_ports import ConstraintSupport, SemanticValidator
from domain_kernel.modeling.domain.interchange import RDF_MAPPING
from domain_kernel.modeling.domain.rdf_graphs import DK, candidate_pin
from domain_kernel.modeling.domain.snapshots import ValidationReport
from domain_kernel.modeling.infrastructure.rdf_messages import CheckShacl
from domain_kernel.modeling.infrastructure.rdflib_adapter import RdfLibAdapter
from domain_kernel.shared.contracts import Issue
from domain_kernel.shared.domain.enums.constraint_language import ConstraintLanguage
from domain_kernel.shared.domain.errors.invalid_ontology_error import InvalidOntologyError
from domain_kernel.shared.domain.errors.missing_dependency_error import MissingDependencyError
from domain_kernel.shared.domain.errors.unsupported_capability_error import (
    UnsupportedCapabilityError,
)
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.ontology_limits import OntologyLimits
from domain_kernel.shared.errors import ResourceLimitError

if TYPE_CHECKING:
    from domain_kernel.modeling.application.interchange import SemanticProjector
    from domain_kernel.modeling.domain.interchange import ValidationGraphs
    from domain_kernel.modeling.domain.snapshots import Candidate
    from domain_kernel.reference_packs.api.packs import ReferencePack

_LOCATION_FIELDS = {
    f"{DK}displayName": "display_name",
    f"{DK}lookupName": "name",
    f"{DK}meaning": "meaning",
    f"{DK}alias": "aliases",
    f"{DK}definitionId": "id",
    f"{DK}revision": "revision",
}


def _library_version(*, distribution: str) -> str:
    try:
        return version(distribution_name=distribution)
    except PackageNotFoundError:
        return "unavailable"


@final
class ShaclModelValidator(SemanticValidator, ConstraintSupport):
    """Validate model metadata and check instance shape syntax without operational data."""

    def __init__(self, *, projector: SemanticProjector | None = None) -> None:
        """Bind the shared mapping and capture the controlled engine fingerprint."""
        self._projector = RdfLibProjector() if projector is None else projector
        self._pyshacl = _library_version(distribution="pyshacl")
        self._rdflib = _library_version(distribution="rdflib")
        self._fingerprint = (
            f"pyshacl/{self._pyshacl}|rdflib/{self._rdflib}|{RDF_MAPPING.value}|core|no-entailment"
        )

    @property
    @override
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    @override
    def constraint_languages(self) -> tuple[ConstraintLanguage, ...]:
        return (ConstraintLanguage.SHACL,)

    @property
    def core_predicates(self) -> tuple[Iri, ...]:
        """Report the authored SHACL Core predicates admitted by this validator."""
        return tuple(Iri(value=value) for value in sorted(SHACL_CORE_PREDICATES))

    @property
    def extensions(self) -> tuple[Iri, ...]:
        """Report available extension vocabularies."""
        return ()

    @property
    def entailment(self) -> str:
        """Report the explicit graph preprocessing mode."""
        return "none"

    @override
    async def validate(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
    ) -> ValidationReport:
        issues = await asyncio.to_thread(
            self._issues,
            candidate=candidate,
            reference_pack=reference_pack,
        )
        return ValidationReport(
            id=ValidationReportId(value=uuid4().hex),
            scope=candidate.scope,
            candidate_id=candidate.id,
            candidate_hash=candidate.content_hash,
            validator_fingerprint=self.fingerprint,
            reference_pack=candidate.reference_pack,
            issues=issues,
        )

    def _issues(
        self,
        *,
        candidate: Candidate,
        reference_pack: ReferencePack | None,
    ) -> tuple[Issue, ...]:
        if "unavailable" in (self._pyshacl, self._rdflib):
            return (
                Issue(
                    code="shacl_capability_missing",
                    path=("validation",),
                    message="Install the SDK ontology extra for the required SHACL validator.",
                ),
            )
        try:
            graphs = self._projector.validation_graphs(
                candidate=candidate,
                reference_pack=reference_pack,
                mapping_version=RDF_MAPPING.value,
            )
            if (
                graphs.candidate != candidate_pin(candidate=candidate)
                or graphs.mapping.id != RDF_MAPPING
            ):
                return (
                    Issue(
                        code="shacl_projection_mismatch",
                        path=("validation",),
                        message="Return validation graphs for the exact candidate and mapping.",
                    ),
                )
            return self._validate_graphs(graphs=graphs)
        except (
            InvalidOntologyError,
            ResourceLimitError,
            MissingDependencyError,
            UnsupportedCapabilityError,
        ):
            return (
                Issue(
                    code="shacl_validation_failed",
                    path=("validation",),
                    message="Review the supported shape syntax and the validation resource budget.",
                ),
            )

    def _validate_graphs(self, *, graphs: ValidationGraphs) -> tuple[Issue, ...]:
        if graphs.issues:
            return tuple(graphs.issues)
        checked = RdfLibAdapter().validate_shacl(
            command=CheckShacl(
                metadata=graphs.model_metadata,
                model_shapes=graphs.model_shapes,
                instance_shapes=graphs.instance_shapes,
                limits=OntologyLimits(timeout_ms=15_000),
            )
        )
        locations = {node: tuple(path) for node, path in graphs.locations}
        issues: list[Issue] = []
        for code, focus, shape, predicate in checked.issues:
            authored = (
                locations.get(shape, ("validation",)) if shape is not None else ("validation",)
            )
            path = (
                locations.get(focus, authored)
                if code == "shacl_violation" and focus is not None
                else authored
            )
            if (
                predicate is not None
                and predicate.value in _LOCATION_FIELDS
                and code == "shacl_violation"
            ):
                path = (*path, _LOCATION_FIELDS[predicate.value])
            issues.append(
                Issue(
                    code=code,
                    path=path,
                    message="Inspect this review-approved model constraint."
                    if code == "shacl_violation"
                    else "Correct the authored SHACL graph structure.",
                )
            )
        return tuple(
            sorted(set(issues), key=lambda item: (item.code, tuple(str(x) for x in item.path)))
        )
