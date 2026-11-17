"""Analyze a requested LinkML capability without installing an adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.bundles import require_valid_bundle
from domain_kernel.modeling.domain.interchange import (
    LINKML_MAPPING,
    ProjectionAvailability,
    ProjectionRemedy,
)
from domain_kernel.modeling.domain.projection_analysis import make_assessment
from domain_kernel.shared.contracts import Issue

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.interchange import (
        LinkmlProjectionRequest,
        ProjectionAssessment,
    )
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle


def assess_linkml(
    *, bundle: DomainModelBundle, request: LinkmlProjectionRequest
) -> ProjectionAssessment:
    """Report the availability of the exact LinkML mapping."""
    require_valid_bundle(bundle=bundle)
    if request.mapping != LINKML_MAPPING:
        availability = ProjectionAvailability.UNSUPPORTED_MAPPING
        remedy = ProjectionRemedy.SELECT_SUPPORTED_MAPPING
        message = "Select the supported dk-linkml/1.0 mapping."
    else:
        availability = ProjectionAvailability.MISSING_DEPENDENCY
        remedy = ProjectionRemedy.INSTALL_OPTIONAL_DEPENDENCY
        message = "Select an SDK release with the LinkML capability installed."
    return make_assessment(
        model=bundle.model_version,
        request=request,
        availability=availability,
        issues=(Issue(code=availability.value, path=("mapping",), message=message),),
        remedies=(remedy,),
    )
