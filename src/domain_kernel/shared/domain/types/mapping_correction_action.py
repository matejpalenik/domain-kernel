"""Type contract for mapping correction action."""

from __future__ import annotations

from domain_kernel.review.domain.decisions import (
    ApproveLocalExtension,
    Exclude,
    MapToDefinition,
    MapToReference,
)
from domain_kernel.shared.domain.operations.map_to_planned_definition import MapToPlannedDefinition

type MappingCorrectionAction = (
    MapToDefinition | MapToReference | ApproveLocalExtension | Exclude | MapToPlannedDefinition
)
