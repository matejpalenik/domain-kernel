"""Scoped idempotency and lease fencing over an operation-local SQLite session."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from sqlalchemy import CheckConstraint, String, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped, mapped_column

from domain_kernel._shared.application.persistence import (
    IdempotencyRepository,
    Lease,
    OperationOutcome,
)
from domain_kernel._shared.infrastructure.sqlite_base import SQLiteBase
from domain_kernel.shared.errors import (
    IdempotencyConflictError,
    OperationInProgressError,
    StaleStateError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

    from domain_kernel._shared.application.persistence import Clock, Invocation

_LEASE_DURATION = timedelta(minutes=1)


@final
class _OperationRow(SQLiteBase):
    __tablename__ = "dk_operation"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(
            """(lease_token IS NULL AND lease_owner IS NULL AND expires_at IS NULL) OR
            (lease_token IS NOT NULL AND lease_owner IS NOT NULL AND expires_at IS NOT NULL)""",
            name="dk_operation_lease_complete",
        ),
        CheckConstraint(
            """(result_kind IS NULL AND result_id IS NULL AND result_version IS NULL) OR
            (result_kind IS NOT NULL AND result_id IS NOT NULL AND lease_token IS NULL)""",
            name="dk_operation_result_complete",
        ),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    # The empty key is reserved for project-scoped operations. ModelId rejects empty values.
    model_key: Mapped[str] = mapped_column(String, primary_key=True)
    operation: Mapped[str] = mapped_column(String, primary_key=True)
    request_key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    lease_token: Mapped[str | None] = mapped_column(String)
    lease_owner: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[str | None] = mapped_column(String)
    result_kind: Mapped[str | None] = mapped_column(String)
    result_id: Mapped[str | None] = mapped_column(String)
    result_version: Mapped[str | None] = mapped_column(String)


def _identity(*, invocation: Invocation) -> dict[str, str]:
    return {
        "project_id": invocation.project_id.value,
        "model_key": invocation.model_id.value if invocation.model_id else "",
        "operation": invocation.operation,
        "request_key": invocation.idempotency_key,
    }


def _scope(*, invocation: Invocation) -> tuple[ColumnElement[bool], ...]:
    return (
        _OperationRow.project_id == invocation.project_id.value,
        _OperationRow.model_key == (invocation.model_id.value if invocation.model_id else ""),
        _OperationRow.operation == invocation.operation,
        _OperationRow.request_key == invocation.idempotency_key,
    )


def _stamp(*, time: datetime) -> str:
    if time.utcoffset() is None:
        raise ValueError("The operation clock must return a time with a time zone")
    return time.astimezone(UTC).isoformat(timespec="microseconds")


def _lease_values(*, lease: Lease | None) -> dict[str, str | None]:
    if lease is None:
        return {"lease_token": None, "lease_owner": None, "expires_at": None}
    return {
        "lease_token": lease.token,
        "lease_owner": lease.owner,
        "expires_at": _stamp(time=lease.expires_at),
    }


@final
class SQLiteIdempotencyRepository(IdempotencyRepository):
    """Read and write durable claims using the caller's existing transaction."""

    def __init__(self, *, session: AsyncSession, clock: Clock) -> None:
        """Bind the session and time provider for one operation."""
        self._session = session
        self._clock = clock

    @override
    async def claim(self, *, invocation: Invocation, owner: str) -> Lease | OperationOutcome:
        # This insert is also the writer gate. Inspecting first would race a concurrent claimant.
        _ = await self._session.execute(
            insert(_OperationRow)
            .values(**_identity(invocation=invocation), request_hash=invocation.request_hash.value)
            .on_conflict_do_nothing(
                index_elements=(
                    _OperationRow.project_id,
                    _OperationRow.model_key,
                    _OperationRow.operation,
                    _OperationRow.request_key,
                )
            ),
        )
        scope = _scope(invocation=invocation)
        row = (await self._session.scalars(select(_OperationRow).where(*scope))).one()
        if row.request_hash != invocation.request_hash.value:
            raise IdempotencyConflictError
        if row.result_kind is not None and row.result_id is not None:
            return OperationOutcome(
                resource_kind=row.result_kind,
                resource_id=row.result_id,
                resource_version=row.result_version,
            )
        now = self._clock()
        if row.expires_at is not None and row.expires_at > _stamp(time=now):
            raise OperationInProgressError
        lease = Lease(token=uuid4().hex, owner=owner, expires_at=now + _LEASE_DURATION)
        _ = await self._session.execute(
            update(_OperationRow).where(*scope).values(**_lease_values(lease=lease))
        )
        return lease

    async def _apply_fenced(
        self,
        *,
        invocation: Invocation,
        lease: Lease,
        values: dict[str, str | None],
    ) -> None:
        updated = await self._session.scalars(
            update(_OperationRow)
            .where(
                *_scope(invocation=invocation),
                _OperationRow.request_hash == invocation.request_hash.value,
                _OperationRow.lease_token == lease.token,
                _OperationRow.lease_owner == lease.owner,
                _OperationRow.expires_at == _stamp(time=lease.expires_at),
                _OperationRow.expires_at > _stamp(time=self._clock()),
            )
            .values(**values)
            .returning(_OperationRow.request_key),
        )
        if updated.one_or_none() is None:
            raise StaleStateError(
                message="The operation lease changed or expired. Reload its outcome or reclaim it."
            )

    @override
    async def complete(
        self, *, invocation: Invocation, lease: Lease, outcome: OperationOutcome
    ) -> None:
        await self._apply_fenced(
            invocation=invocation,
            lease=lease,
            values={
                **_lease_values(lease=None),
                "result_kind": outcome.resource_kind,
                "result_id": outcome.resource_id,
                "result_version": outcome.resource_version,
            },
        )

    @override
    async def renew(self, *, invocation: Invocation, lease: Lease) -> Lease:
        renewed = Lease(
            token=uuid4().hex, owner=lease.owner, expires_at=self._clock() + _LEASE_DURATION
        )
        await self._apply_fenced(
            invocation=invocation, lease=lease, values=_lease_values(lease=renewed)
        )
        return renewed

    @override
    async def release(self, *, invocation: Invocation, lease: Lease) -> None:
        await self._apply_fenced(
            invocation=invocation, lease=lease, values=_lease_values(lease=None)
        )
