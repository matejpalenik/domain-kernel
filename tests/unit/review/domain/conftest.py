"""Provide the pending review case shared by domain policy checks."""

from __future__ import annotations

import pytest

from domain_kernel import (
    CaseKind,
    CaseStatus,
    ReviewCaseId,
)
from domain_kernel.review.domain.models import (
    ReviewCase,
)
from tests.support.modeling.machine_definition import make_machine_definition


@pytest.fixture
def proposal() -> ReviewCase:
    definition = make_machine_definition()
    return ReviewCase(
        id=ReviewCaseId(value="review"),
        scope=definition.scope,
        version=1,
        status=CaseStatus.PENDING,
        kind=CaseKind.PROPOSAL,
        definitions=[definition],
        reason="Owner-authored meaning.",
    )
