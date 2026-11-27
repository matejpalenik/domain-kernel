"""Verification of durable citation references before content or review use."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.shared.errors.missing_capability_error import MissingCapabilityError
from domain_kernel.shared.errors.scope_mismatch_error import ScopeMismatchError
from domain_kernel.sources.application.ports import ParsedSourceRepository
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)

if TYPE_CHECKING:
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.sources.application.ports import SourceRepository
    from domain_kernel.sources.domain.models import Evidence


async def recorded_citation(
    *, repository: SourceRepository, project_id: ProjectId, expected: Evidence
) -> Evidence:
    """Verify the exact citation, project and revision without retrieving its content."""
    if expected.source.project_id != project_id:
        raise ScopeMismatchError
    if not isinstance(repository, ParsedSourceRepository):
        raise MissingCapabilityError(message="Configure source citation persistence")
    recorded = await repository.evidence(project_id=project_id, identity=expected.id)
    if recorded is None or recorded != expected:
        raise EvidenceUnavailableError
    revision = await repository.revision(
        project_id=project_id,
        source_id=recorded.source.source_id,
        revision_id=recorded.source.revision_id,
    )
    if revision != recorded.source:
        raise SourceRevisionMismatchError
    return recorded
