"""Journal external delivery independently of the persisted resources it copies."""

from __future__ import annotations

import asyncio
from abc import ABCMeta, abstractmethod
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

from domain_kernel.shared.application.persistence import (
    Invocation,
    Lease,
    OperationOutcome,
    keep_work_leased,
)
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.errors.artifact_conflict_error import ArtifactConflictError
from domain_kernel.shared.errors import DomainKernelError, MissingCapabilityError, StaleStateError
from domain_kernel.shared.hashing import hash_json
from domain_kernel.shared.identifiers.audit_id import AuditId

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from domain_kernel.shared.application.persistence import Transaction
    from domain_kernel.shared.domain.enums.audit_action import AuditAction
    from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
    from domain_kernel.shared.hashing import JsonValue


_HEARTBEAT_SECONDS = 20


@runtime_checkable
class ArtifactAudit(Protocol):
    """Read exact audit snapshots used by resumable delivery."""

    async def get(self, *, audit_id: AuditId) -> AuditRecord | None:
        """Return the saved event by its durable identity."""


class ArtifactWriter(Protocol, metaclass=ABCMeta):
    """Write a new artifact or recover an interrupted request."""

    @abstractmethod
    async def __call__(self, *, retry: bool) -> Artifact:
        """Return the receipt for the exact delivery request."""


@dataclass(frozen=True, kw_only=True)
class DeliveryRequest:
    """The stable external intent after preflight has verified its source."""

    action: AuditAction
    actor: str
    idempotency_key: str | None
    intent: JsonValue
    requested: Artifact
    resource: AuditResource

    def invocation(self) -> Invocation:
        """Bind source, location and attribution to one scope-local key."""
        return Invocation.resolve(
            project_id=self.requested.project_id,
            model_id=self.requested.model_id,
            operation=self.action.value,
            actor=self.actor,
            key=self.idempotency_key,
            intent=self.intent,
        )

    def record(
        self,
        *,
        audit_id: AuditId,
        outcome: AuditOutcome,
        parent: AuditId | None = None,
        artifact: Artifact | None = None,
    ) -> AuditRecord:
        """Capture one attributed transition with verified effects when available."""
        return AuditRecord(
            id=audit_id,
            project_id=self.requested.project_id,
            model_id=self.requested.model_id,
            action=self.action,
            outcome=outcome,
            actor=self.actor,
            recorded_at=datetime.now(tz=UTC),
            before=(self.resource,),
            after=() if artifact is None else (artifact,),
            requested_artifact=self.requested,
            parent_id=parent,
        )


def _started_id(*, invocation: Invocation) -> AuditId:
    digest = hash_json(
        value=(
            "artifact-delivery",
            invocation.project_id.value,
            invocation.model_id.value if invocation.model_id is not None else None,
            invocation.operation,
            invocation.idempotency_key,
        )
    )
    return AuditId(value=digest.value.removeprefix("sha256:"))


@dataclass(frozen=True, kw_only=True)
class DeliveryReceipt:
    """The exact verified artifact and its committed acknowledgement time."""

    artifact: Artifact
    recorded_at: datetime


async def _check_receipt(
    *,
    requested: Artifact,
    actual: Artifact,
    verify: Callable[[Artifact], Awaitable[bool]],
) -> None:
    if (
        type(actual) is not Artifact
        or requested != replace(actual, provider_version=None)
        or not await verify(actual)
    ):
        raise ArtifactConflictError


async def deliver(
    *,
    transaction: Transaction,
    request: DeliveryRequest,
    write: ArtifactWriter,
    verify: Callable[[Artifact], Awaitable[bool]],
) -> DeliveryReceipt:
    """Fence receipts and verify bytes before recording success or replaying a result."""
    audit = transaction.audit
    if not isinstance(audit, ArtifactAudit):
        raise MissingCapabilityError(message="Configure persistence for durable artifact delivery")
    invocation = request.invocation()
    started_id = _started_id(invocation=invocation)
    receipt: AuditRecord | None = None
    started: AuditRecord | None = None
    async with transaction.begin():
        claim = await transaction.operations.claim(invocation=invocation, owner=uuid4().hex)
        if isinstance(claim, Lease):
            started = await audit.get(audit_id=started_id)
            if started is None:
                await transaction.audit.append(
                    record=request.record(
                        audit_id=started_id,
                        outcome=AuditOutcome.STARTED,
                    )
                )
        else:
            receipt = await audit.get(audit_id=AuditId(value=claim.resource_id))
    if isinstance(claim, OperationOutcome):
        if (
            receipt is None
            or receipt.parent_id != started_id
            or receipt.outcome is not AuditOutcome.SUCCEEDED
            or receipt.requested_artifact != request.requested
            or len(receipt.after) != 1
            or not isinstance(actual := receipt.after[0], Artifact)
        ):
            raise StaleStateError(message="Inspect the exact stored artifact receipt")
        await _check_receipt(requested=request.requested, actual=actual, verify=verify)
        return DeliveryReceipt(artifact=actual, recorded_at=receipt.recorded_at)
    lease = claim

    async def renew() -> None:
        nonlocal lease
        async with transaction.begin():
            updated = await transaction.operations.renew(invocation=invocation, lease=lease)
        lease = updated

    async def transfer() -> Artifact:
        artifact = await write(retry=started is not None)
        await _check_receipt(requested=request.requested, actual=artifact, verify=verify)
        return artifact

    try:
        actual = await keep_work_leased(work=transfer(), renew=renew, interval=_HEARTBEAT_SECONDS)
        result = request.record(
            audit_id=AuditId(value=uuid4().hex),
            outcome=AuditOutcome.SUCCEEDED,
            parent=started_id,
            artifact=actual,
        )
        async with transaction.begin():
            await transaction.operations.complete(
                invocation=invocation,
                lease=lease,
                outcome=OperationOutcome(resource_kind="artifact", resource_id=result.id.value),
            )
            await transaction.audit.append(record=result)
    except (Exception, asyncio.CancelledError):
        with suppress(DomainKernelError):
            async with transaction.begin():
                await transaction.operations.release(invocation=invocation, lease=lease)
                await transaction.audit.append(
                    record=request.record(
                        audit_id=AuditId(value=uuid4().hex),
                        outcome=AuditOutcome.FAILED,
                        parent=started_id,
                    )
                )
        raise
    return DeliveryReceipt(artifact=actual, recorded_at=result.recorded_at)
