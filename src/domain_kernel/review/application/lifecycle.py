"""Capture one reviewed definition lifecycle operation from exact repository values."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel.review.domain.enums.case_kind import CaseKind
from domain_kernel.review.domain.enums.case_status import CaseStatus
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.review.domain.models import ReviewCase
from domain_kernel.shared.domain.value_objects.plans.restore_definition import RestoreDefinition
from domain_kernel.shared.domain.value_objects.plans.retire_definition import RetireDefinition
from domain_kernel.shared.errors.stale_state_error import StaleStateError

if TYPE_CHECKING:
    from domain_kernel.review.application.ports import DefinitionRepository
    from domain_kernel.shared.domain.entities.definition import Definition
    from domain_kernel.shared.domain.types.lifecycle_operation import LifecycleOperation


async def check_inspected(*, repository: DefinitionRepository, before: Definition) -> None:
    """Require the exact captured record to still be the current definition revision."""
    current = await repository.get(
        scope=before.scope,
        definition_id=before.id,
        name=None,
        revision=None,
    )
    if current != before:
        raise StaleStateError(message="Reload and inspect the current definition revision")


def lifecycle_case(
    *,
    operation: LifecycleOperation,
    grouped_by_case_id: ReviewCaseId | None = None,
) -> ReviewCase:
    """Build the pending lifecycle case without applying effects."""
    if isinstance(operation, RetireDefinition):
        kind = CaseKind.DEFINITION_RETIREMENT
    elif isinstance(operation, RestoreDefinition):
        kind = CaseKind.DEFINITION_RESTORATION
    else:
        kind = CaseKind.DEFINITION_REVISION
    return ReviewCase(
        id=ReviewCaseId(value=uuid4().hex),
        scope=operation.before.scope,
        kind=kind,
        status=CaseStatus.PENDING,
        version=1,
        definitions=(operation.draft(),),
        before_definition=operation.before,
        reason=operation.reason,
        grouped_by_case_id=grouped_by_case_id,
    )
