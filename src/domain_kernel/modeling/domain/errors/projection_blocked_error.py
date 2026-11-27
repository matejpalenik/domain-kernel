"""Failure to export a model under the requested mapping."""

from __future__ import annotations

from domain_kernel.modeling.domain.interchange import ProjectionAssessment
from domain_kernel.shared.errors.unsupported_capability_error import UnsupportedCapabilityError
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


class ProjectionBlockedError(UnsupportedCapabilityError):
    """The requested mapping did not produce an exportable assessment."""

    def __init__(self, *, assessment: ProjectionAssessment) -> None:
        """Keep the exact report for recovery or selection of a different target."""
        RuntimeTypeValidation.require_exact(
            value=assessment, expected=ProjectionAssessment, field="Projection assessment"
        )
        if assessment.exportable:
            raise ValueError("Use the failed projection report")
        self.assessment: ProjectionAssessment = assessment
        super().__init__(message="Inspect the projection findings and select a supported export.")
