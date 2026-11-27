from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from sqlalchemy import (
    select,
    update,
)

from domain_kernel.modeling.domain.errors.model_not_found_error import ModelNotFoundError
from domain_kernel.shared.application.protocols.workspace_revisions import WorkspaceRevisions
from domain_kernel.shared.errors.stale_state_error import StaleStateError
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope

from domain_kernel.shared.infrastructure.persistence.rows.model_row import ModelRow


@final
class SqlAlchemyWorkspaceRevisions(WorkspaceRevisions):
    """Compare and advance a persisted workspace revision within the caller's transaction."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind the operation-local session."""
        self._session = session

    @override
    async def revision(self, *, scope: ModelScope) -> int:
        """Read the current revision of the exact project and model scope."""
        value = await self._session.scalar(
            select(ModelRow.revision).where(
                ModelRow.project_id == scope.project_id.value,
                ModelRow.id == scope.model_id.value,
            )
        )
        if value is None:
            raise ModelNotFoundError

        return value

    @override
    async def advance(self, *, scope: ModelScope, expected_revision: int) -> None:
        """Increment the scoped revision when the expected revision still matches."""
        RuntimeTypeValidation.require_exact(
            value=expected_revision, expected=int, field="Expected workspace revision"
        )
        if expected_revision < 0:
            raise ValueError("Expected workspace revision must be nonnegative")

        value = await self._session.scalar(
            update(ModelRow)
            .where(
                ModelRow.project_id == scope.project_id.value,
                ModelRow.id == scope.model_id.value,
                ModelRow.revision == expected_revision,
            )
            .values(revision=ModelRow.revision + 1)
            .returning(ModelRow.revision)
        )
        if value is None:
            raise StaleStateError
