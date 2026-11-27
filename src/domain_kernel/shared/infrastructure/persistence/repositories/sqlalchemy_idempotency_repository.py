from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from sqlalchemy import select, update

from domain_kernel.shared.application.idempotency.idempotency_conflict_error import (
    IdempotencyConflictError,
)
from domain_kernel.shared.application.idempotency.lease import Lease
from domain_kernel.shared.application.idempotency.operation_in_progress_error import (
    OperationInProgressError,
)
from domain_kernel.shared.application.idempotency.operation_outcome import OperationOutcome
from domain_kernel.shared.application.protocols.idempotency_repository import IdempotencyRepository
from domain_kernel.shared.errors.stale_state_error import StaleStateError
from domain_kernel.shared.infrastructure.persistence.sql_insert import SqlInsert

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

    from domain_kernel.shared.application.idempotency.clock import Clock
    from domain_kernel.shared.application.idempotency.invocation import Invocation

from domain_kernel.shared.infrastructure.persistence.rows.operation_row import OperationRow

_LEASE_DURATION = timedelta(minutes=1)


@final
class SqlAlchemyIdempotencyRepository(IdempotencyRepository):
    """Read and write durable claims using the caller's existing transaction."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        """Bind the session and time provider for one operation."""
        self._session = session
        self._clock = clock

    @override
    async def claim(self, *, invocation: Invocation, owner: str) -> Lease | OperationOutcome:
        """Return a matching prior outcome or acquire time-limited commit authority."""
        # This insert is also the writer gate. Inspecting first would race a concurrent claimant.
        _ = await self._session.execute(
            SqlInsert.for_session(session=self._session, row=OperationRow)
            .values(
                **self._identity(invocation=invocation), request_hash=invocation.request_hash.value
            )
            .on_conflict_do_nothing(
                index_elements=(
                    OperationRow.project_id,
                    OperationRow.model_key,
                    OperationRow.operation,
                    OperationRow.request_key,
                )
            ),
        )

        scope = self._scope(invocation=invocation)
        row = (await self._session.scalars(select(OperationRow).where(*scope))).one()
        if row.request_hash != invocation.request_hash.value:
            raise IdempotencyConflictError

        if row.result_kind is not None and row.result_id is not None:
            return OperationOutcome(
                resource_kind=row.result_kind,
                resource_id=row.result_id,
                resource_version=row.result_version,
            )

        now = self._clock()
        if row.expires_at is not None and row.expires_at > self._stamp(time=now):
            raise OperationInProgressError

        lease = Lease(token=uuid4().hex, owner=owner, expires_at=now + _LEASE_DURATION)
        _ = await self._session.execute(
            update(OperationRow).where(*scope).values(**self._lease_values(lease=lease))
        )

        return lease

    async def _apply_fenced(
        self,
        *,
        invocation: Invocation,
        lease: Lease,
        values: dict[str, str | None],
    ) -> None:
        """Apply the write only while the exact lease remains current and unexpired."""
        updated = await self._session.scalars(
            update(OperationRow)
            .where(
                *self._scope(invocation=invocation),
                OperationRow.request_hash == invocation.request_hash.value,
                OperationRow.lease_token == lease.token,
                OperationRow.lease_owner == lease.owner,
                OperationRow.expires_at == self._stamp(time=lease.expires_at),
                OperationRow.expires_at > self._stamp(time=self._clock()),
            )
            .values(**values)
            .returning(OperationRow.request_key),
        )
        if updated.one_or_none() is None:
            raise StaleStateError(
                message="The operation lease changed or expired. Reload its outcome or reclaim it."
            )

    @override
    async def complete(
        self, *, invocation: Invocation, lease: Lease, outcome: OperationOutcome
    ) -> None:
        """Record the outcome while the invocation still owns the lease."""
        await self._apply_fenced(
            invocation=invocation,
            lease=lease,
            values={
                **self._lease_values(lease=None),
                "result_kind": outcome.resource_kind,
                "result_id": outcome.resource_id,
                "result_version": outcome.resource_version,
            },
        )

    @override
    async def renew(self, *, invocation: Invocation, lease: Lease) -> Lease:
        """Extend the live lease for this invocation and return its new expiry."""
        renewed = Lease(
            token=uuid4().hex, owner=lease.owner, expires_at=self._clock() + _LEASE_DURATION
        )
        await self._apply_fenced(
            invocation=invocation, lease=lease, values=self._lease_values(lease=renewed)
        )

        return renewed

    @override
    async def release(self, *, invocation: Invocation, lease: Lease) -> None:
        """Clear the lease if this invocation still owns it."""
        await self._apply_fenced(
            invocation=invocation, lease=lease, values=self._lease_values(lease=None)
        )

    @staticmethod
    def _identity(*, invocation: Invocation) -> dict[str, str]:
        """Return the durable key and scope columns of the operation."""
        return {
            "project_id": invocation.project_id.value,
            "model_key": invocation.model_id.value if invocation.model_id else "",
            "operation": invocation.operation,
            "request_key": invocation.idempotency_key,
        }

    @staticmethod
    def _scope(*, invocation: Invocation) -> tuple[ColumnElement[bool], ...]:
        """Build the SQL predicates that match the operation's exact identity."""
        return (
            OperationRow.project_id == invocation.project_id.value,
            OperationRow.model_key == (invocation.model_id.value if invocation.model_id else ""),
            OperationRow.operation == invocation.operation,
            OperationRow.request_key == invocation.idempotency_key,
        )

    @staticmethod
    def _stamp(*, time: datetime) -> str:
        """Normalize a timestamp to the UTC representation used by lease comparisons."""
        if time.utcoffset() is None:
            raise ValueError("The operation clock must return a time with a time zone")

        return time.astimezone(UTC).isoformat(timespec="microseconds")

    @staticmethod
    def _lease_values(*, lease: Lease | None) -> dict[str, str | None]:
        """Encode the current holder or clear the persisted lease fields."""
        if lease is None:
            return {"lease_token": None, "lease_owner": None, "expires_at": None}

        return {
            "lease_token": lease.token,
            "lease_owner": lease.owner,
            "expires_at": SqlAlchemyIdempotencyRepository._stamp(time=lease.expires_at),
        }
