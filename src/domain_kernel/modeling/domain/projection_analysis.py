"""Report exact mapping support and consumer responsibilities for published shapes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel._shared.domain.model_values import MeaningText
from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.modeling.domain.interchange import (
    ProjectionAssessment,
    ProjectionAvailability,
    ProjectionFinding,
    ProjectionRemedy,
    RepresentationSupport,
    ValidationResponsibility,
)
from domain_kernel.shared.hashing import hash_json

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.artifacts import ConsumerObligation
    from domain_kernel.modeling.domain.interchange import (
        MappingDescriptor,
        ProjectionFeature,
        ProjectionLocation,
        ProjectionRequest,
    )
    from domain_kernel.shared.contracts import Issue, ModelVersion


def blocked_feature(
    *,
    location: ProjectionLocation,
    feature: ProjectionFeature,
    message: str,
) -> ProjectionFinding:
    """Explain an exact meaning that the selected mapping would lose."""
    return ProjectionFinding(
        location=location,
        feature=feature,
        representation=RepresentationSupport.UNSUPPORTED,
        validation=ValidationResponsibility.UNSUPPORTED,
        explanation=MeaningText(value=message),
        next_steps=(
            ProjectionRemedy.USE_COMPLETE_BUNDLE,
            ProjectionRemedy.AUTHOR_REVIEWED_DERIVATION,
        ),
    )


def host_feature(
    *,
    location: ProjectionLocation,
    feature: ProjectionFeature,
    message: str,
    obligation: ConsumerObligation,
) -> ProjectionFinding:
    """Carry an explicitly typed duty that requires the consuming application."""
    return ProjectionFinding(
        location=location,
        feature=feature,
        representation=RepresentationSupport.ANNOTATED,
        validation=ValidationResponsibility.HOST,
        explanation=MeaningText(value=message),
        obligations=(obligation,),
        next_steps=(ProjectionRemedy.ENFORCE_IN_HOST,),
    )


def make_assessment(  # noqa: PLR0913 - Bind the complete assessment and exact mapping inputs.
    *,
    model: ModelVersion,
    request: ProjectionRequest,
    availability: ProjectionAvailability,
    mapping: MappingDescriptor | None = None,
    findings: Sequence[ProjectionFinding] = (),
    issues: Sequence[Issue] = (),
    remedies: Sequence[ProjectionRemedy] = (),
) -> ProjectionAssessment:
    """Create a deterministic report bound to the exact analyzed inputs."""
    duties = tuple(dict.fromkeys(item for row in findings for item in row.obligations))
    next_steps = tuple(
        dict.fromkeys((*remedies, *(item for row in findings for item in row.next_steps)))
    )
    digest = hash_json(
        value=record_value(
            value=(
                "domain-kernel.projection-assessment.v1",
                model,
                request,
                availability,
                mapping,
                tuple(findings),
                duties,
                tuple(issues),
                next_steps,
            ),
        )
    )
    return ProjectionAssessment(
        model=model,
        request=request,
        availability=availability,
        mapping=mapping,
        findings=findings,
        consumer_obligations=duties,
        issues=issues,
        next_steps=next_steps,
        content_hash=digest,
    )
