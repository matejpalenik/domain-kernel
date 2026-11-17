"""Exercise replay and lease fencing over independent database transactions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from domain_kernel import ProjectId, StaleStateError
from domain_kernel._shared.application.persistence import Invocation, Lease, OperationOutcome
from domain_kernel.shared.errors import IdempotencyConflictError, OperationInProgressError

if TYPE_CHECKING:
    from tests.integration.conftest import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _invoke(*, actor: str = "editor", key: str | None = "workflow") -> Invocation:
    return Invocation.resolve(
        project_id=ProjectId(value="recruitment"),
        model_id=None,
        operation="register-source",
        actor=actor,
        key=key,
        intent={"name": "ai-act-en"},
    )


async def test_concurrent_matching_requests_replay_a_single_outcome(
    database_backend: DatabaseBackend,
) -> None:
    invocation = _invoke()

    async def request(*, owner: str) -> OperationOutcome:
        factory = database_backend.factory()
        async with factory() as transaction, transaction.begin():
            claim = await transaction.operations.claim(invocation=invocation, owner=owner)
            if isinstance(claim, OperationOutcome):
                return claim
            outcome = OperationOutcome(resource_kind="source", resource_id=owner)
            await transaction.operations.complete(
                invocation=invocation, lease=claim, outcome=outcome
            )
            return outcome

    results = await asyncio.gather(*(request(owner=f"worker-{i}") for i in range(6)))
    assert len(set(results)) == 1
    factory = database_backend.factory()
    async with factory() as transaction, transaction.begin():
        with pytest.raises(IdempotencyConflictError):
            _ = await transaction.operations.claim(
                invocation=_invoke(actor="reviewer"), owner="retry"
            )


async def test_claim_renewal_release_and_expiry_are_fenced(
    database_backend: DatabaseBackend,
) -> None:
    now = datetime(2026, 11, 16, tzinfo=UTC)

    def clock() -> datetime:
        return now

    factory = database_backend.factory(clock=clock)
    invocation = _invoke()
    async with factory() as transaction, transaction.begin():
        initial = await transaction.operations.claim(invocation=invocation, owner="worker-a")
    assert isinstance(initial, Lease)

    now += timedelta(seconds=1)
    async with factory() as transaction, transaction.begin():
        with pytest.raises(OperationInProgressError):
            _ = await transaction.operations.claim(invocation=invocation, owner="worker-b")
        renewed = await transaction.operations.renew(invocation=invocation, lease=initial)
        with pytest.raises(StaleStateError):
            await transaction.operations.release(invocation=invocation, lease=initial)
    assert renewed.expires_at > initial.expires_at

    now = renewed.expires_at
    async with factory() as transaction, transaction.begin():
        next_lease = await transaction.operations.claim(invocation=invocation, owner="worker-b")
        assert isinstance(next_lease, Lease)
        assert next_lease.token != renewed.token
        with pytest.raises(StaleStateError):
            await transaction.operations.complete(
                invocation=invocation,
                lease=renewed,
                outcome=OperationOutcome(resource_kind="source", resource_id="expired"),
            )
        await transaction.operations.release(invocation=invocation, lease=next_lease)

    async with factory() as transaction, transaction.begin():
        with pytest.raises(IdempotencyConflictError):
            _ = await transaction.operations.claim(
                invocation=_invoke(actor="reviewer"), owner="retry"
            )
        assert isinstance(
            await transaction.operations.claim(invocation=invocation, owner="worker-c"),
            Lease,
        )


async def test_outcome_rolls_back_with_transaction(database_backend: DatabaseBackend) -> None:
    factory = database_backend.factory()
    first, second = _invoke(key=None), _invoke(key=None)
    assert first.request_hash == second.request_hash
    assert first.idempotency_key != second.idempotency_key

    async def write_and_fail() -> None:
        async with factory() as transaction, transaction.begin():
            lease = await transaction.operations.claim(invocation=first, owner="worker")
            assert isinstance(lease, Lease)
            await transaction.operations.complete(
                invocation=first,
                lease=lease,
                outcome=OperationOutcome(resource_kind="source", resource_id="rolled-back"),
            )
            raise RuntimeError("transaction interrupted")

    with pytest.raises(RuntimeError, match="transaction interrupted"):
        await write_and_fail()

    async with factory() as transaction, transaction.begin():
        assert isinstance(
            await transaction.operations.claim(invocation=first, owner="retry"), Lease
        )


@pytest.mark.parametrize("cancel_at", ["before_commit", "during_commit", "after_commit"])
async def test_cancellation_retains_transaction_ownership(
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
    cancel_at: str,
) -> None:
    factory = database_backend.factory()
    invocation = _invoke()
    outcome = OperationOutcome(resource_kind="source", resource_id="registered")
    reached_boundary = asyncio.Event()
    release_boundary = asyncio.Event()
    real_commit = AsyncSession.commit

    async def wait_at_boundary() -> None:
        reached_boundary.set()
        _ = await release_boundary.wait()

    async def controlled_commit(session: AsyncSession) -> None:
        if cancel_at == "during_commit":
            await wait_at_boundary()
        await real_commit(session)
        if cancel_at == "after_commit":
            await wait_at_boundary()

    async def request() -> None:
        async with factory() as transaction, transaction.begin():
            lease = await transaction.operations.claim(invocation=invocation, owner="worker")
            assert isinstance(lease, Lease)
            await transaction.operations.complete(
                invocation=invocation, lease=lease, outcome=outcome
            )
            if cancel_at == "before_commit":
                await wait_at_boundary()

    with monkeypatch.context() as replacement:
        replacement.setattr(AsyncSession, "commit", controlled_commit)
        async with asyncio.timeout(5):
            task = asyncio.create_task(request())
            try:
                _ = await reached_boundary.wait()
            finally:
                _ = task.cancel()
                release_boundary.set()
                with pytest.raises(asyncio.CancelledError):
                    await task

    async with factory() as transaction, transaction.begin():
        replay = await transaction.operations.claim(invocation=invocation, owner="retry")
        if cancel_at == "before_commit":
            assert isinstance(replay, Lease)
        else:
            assert replay == outcome
