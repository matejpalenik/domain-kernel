"""Coordinate durable delivery without holding a transaction across external I/O."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel.shared.application.errors.artifact_conflict_error import ArtifactConflictError
from domain_kernel.shared.application.idempotency.lease import Lease
from domain_kernel.shared.application.idempotency.lease_renewal import LeaseRenewal
from domain_kernel.shared.application.idempotency.operation_outcome import OperationOutcome
from domain_kernel.shared.application.protocols.artifact_audit import ArtifactAudit
from domain_kernel.shared.application.protocols.deliver_artifact import DeliverArtifact
from domain_kernel.shared.application.results.delivery_receipt import DeliveryReceipt
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.errors.domain_kernel_error import DomainKernelError
from domain_kernel.shared.errors.missing_capability_error import MissingCapabilityError
from domain_kernel.shared.errors.stale_state_error import StaleStateError
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.identifiers.audit_id import AuditId

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from domain_kernel.shared.application.commands.deliver_artifact_command import (
        DeliverArtifactCommand,
    )
    from domain_kernel.shared.application.idempotency.invocation import Invocation
    from domain_kernel.shared.application.protocols.artifact_writer import ArtifactWriter
    from domain_kernel.shared.application.protocols.audit_repository import AuditRepository
    from domain_kernel.shared.application.protocols.idempotency_repository import (
        IdempotencyRepository,
    )
    from domain_kernel.shared.application.protocols.transaction_manager import TransactionManager
    from domain_kernel.shared.domain.entities.audit_record import AuditRecord

_HEARTBEAT_SECONDS = 20


@final
class DeliverArtifactService(DeliverArtifact):
    """Journal transfer intent and verify receipts using one operation's resources."""

    def __init__(
        self,
        *,
        audit: AuditRepository,
        operations: IdempotencyRepository,
        transaction: TransactionManager,
    ) -> None:
        """Bind the audit and idempotency ports over the operation's transaction."""
        self._audit = audit
        self._operations = operations
        self._transaction = transaction

    @override
    async def deliver(
        self,
        *,
        request: DeliverArtifactCommand,
        write: ArtifactWriter,
        verify: Callable[[Artifact], Awaitable[bool]],
    ) -> DeliveryReceipt:
        """Fence receipts and verify bytes before recording success or replaying a result."""
        audit = self._audit
        if not isinstance(audit, ArtifactAudit):
            raise MissingCapabilityError(
                message="Configure persistence for durable artifact delivery"
            )

        invocation = request.invocation()
        started_id = self._started_id(invocation=invocation)

        receipt: AuditRecord | None = None
        started: AuditRecord | None = None

        async with self._transaction.begin():
            claim = await self._operations.claim(invocation=invocation, owner=uuid4().hex)
            if isinstance(claim, Lease):
                started = await audit.get(audit_id=started_id)
                if started is None:
                    await self._audit.append(
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

            await self._check_receipt(requested=request.requested, actual=actual, verify=verify)

            return DeliveryReceipt(artifact=actual, recorded_at=receipt.recorded_at)

        lease = claim

        async def renew() -> None:
            """Renew the current claim in a short transaction and capture its new expiry."""
            nonlocal lease
            async with self._transaction.begin():
                updated = await self._operations.renew(invocation=invocation, lease=lease)

            lease = updated

        async def transfer() -> Artifact:
            """Recover or write the artifact and verify its receipt outside the transaction."""
            artifact = await write(retry=started is not None)
            await self._check_receipt(requested=request.requested, actual=artifact, verify=verify)

            return artifact

        try:
            actual = await LeaseRenewal.run(
                work=transfer(), renew=renew, interval=_HEARTBEAT_SECONDS
            )

            result = request.record(
                audit_id=AuditId(value=uuid4().hex),
                outcome=AuditOutcome.SUCCEEDED,
                parent=started_id,
                artifact=actual,
            )

            async with self._transaction.begin():
                await self._operations.complete(
                    invocation=invocation,
                    lease=lease,
                    outcome=OperationOutcome(resource_kind="artifact", resource_id=result.id.value),
                )
                await self._audit.append(record=result)
        except (Exception, asyncio.CancelledError):
            with suppress(DomainKernelError):
                async with self._transaction.begin():
                    await self._operations.release(invocation=invocation, lease=lease)
                    await self._audit.append(
                        record=request.record(
                            audit_id=AuditId(value=uuid4().hex),
                            outcome=AuditOutcome.FAILED,
                            parent=started_id,
                        )
                    )

            raise

        return DeliveryReceipt(artifact=actual, recorded_at=result.recorded_at)

    @staticmethod
    def _started_id(*, invocation: Invocation) -> AuditId:
        """Derive the same start-event identity for every attempt of the invocation."""
        digest = Hashing.hash_json(
            value=(
                "artifact-delivery",
                invocation.project_id.value,
                invocation.model_id.value if invocation.model_id is not None else None,
                invocation.operation,
                invocation.idempotency_key,
            )
        )

        return AuditId(value=digest.value.removeprefix("sha256:"))

    @staticmethod
    async def _check_receipt(
        *,
        requested: Artifact,
        actual: Artifact,
        verify: Callable[[Artifact], Awaitable[bool]],
    ) -> None:
        """Match a delivery or replay receipt to the request and verify the stored bytes.

        Compare metadata with the provider-assigned version removed. Pass the full
        receipt to ``verify`` so it can check the exact stored version.

        Raises:
            ArtifactConflictError: The receipt differs from the request or verification fails.
        """
        if (
            type(actual) is not Artifact
            or requested != replace(actual, provider_version=None)
            or not await verify(actual)
        ):
            raise ArtifactConflictError
