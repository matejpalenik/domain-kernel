"""Resource and transaction ports for operation-local persistence."""

from __future__ import annotations

import asyncio
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self
from uuid import uuid4

from domain_kernel.shared.hashing import hash_json

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine
    from contextlib import AbstractAsyncContextManager
    from datetime import datetime

    from domain_kernel._shared.domain.audit import AuditRecord
    from domain_kernel.modeling.domain.identifiers.model_id import ModelId
    from domain_kernel.projects.domain.identifiers.project_id import ProjectId
    from domain_kernel.shared.contracts import ModelScope, Page
    from domain_kernel.shared.hashing import JsonValue
    from domain_kernel.shared.identifiers.audit_id import AuditId
    from domain_kernel.shared.identifiers.content_hash import ContentHash
    from domain_kernel.shared.identifiers.page_cursor import PageCursor


type Clock = Callable[[], datetime]
type IdentifierFactory[IdT] = Callable[[], IdT]


async def keep_work_leased[T](
    *,
    work: Coroutine[object, object, T],
    renew: Callable[[], Awaitable[None]],
    interval: float,
) -> T:
    """Renew during external work and finish cancelling the child before releasing its lease."""
    child = asyncio.create_task(work)
    try:
        while True:
            done, _ = await asyncio.wait((child,), timeout=interval)
            if done:
                return child.result()
            await renew()
    finally:
        if not child.done():
            _ = child.cancel()
        _ = await asyncio.gather(child, return_exceptions=True)


def _require_nonblank(*, value: object, field: str) -> None:
    if type(value) is not str:
        message = f"{field} must be an exact string"
        raise TypeError(message)
    if not value.strip():
        message = f"{field} must not be blank"
        raise ValueError(message)


@dataclass(frozen=True, kw_only=True)
class Invocation:
    """Resolved operation identity used throughout retries and checkpoints."""

    project_id: ProjectId
    model_id: ModelId | None
    operation: str
    idempotency_key: str
    request_hash: ContentHash
    actor: str
    parent_audit_id: AuditId | None = None

    def __post_init__(self) -> None:
        """Require explicit attribution and a resolved operation and key."""
        _require_nonblank(value=self.actor, field="Actor")
        _require_nonblank(value=self.operation, field="Operation")
        _require_nonblank(value=self.idempotency_key, field="Idempotency key")

    @classmethod
    def resolve(  # noqa: PLR0913 - All resolved scope and attribution fields are explicit.
        cls,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        operation: str,
        actor: str,
        key: str | None,
        intent: JsonValue,
        parent_audit_id: AuditId | None = None,
    ) -> Self:
        """Bind this key to the exact actor, parent, and canonical command intent."""
        return cls(
            project_id=project_id,
            model_id=model_id,
            operation=operation,
            idempotency_key=uuid4().hex if key is None else key,
            request_hash=hash_json(
                value={
                    "actor": actor,
                    "intent": intent,
                    "parent_audit_id": parent_audit_id.value if parent_audit_id else None,
                }
            ),
            actor=actor,
            parent_audit_id=parent_audit_id,
        )


@dataclass(frozen=True, kw_only=True)
class Lease:
    """Time-limited commit authority issued to one operation worker."""

    token: str
    owner: str
    expires_at: datetime

    def __post_init__(self) -> None:
        """Reject empty holders and ambiguous timestamps."""
        _require_nonblank(value=self.token, field="Lease token")
        _require_nonblank(value=self.owner, field="Lease owner")
        if self.expires_at.utcoffset() is None:
            raise ValueError("Lease expiry must include a time zone")


@dataclass(frozen=True, kw_only=True)
class OperationOutcome:
    """Detached identity of the exact result committed for a durable request."""

    resource_kind: str
    resource_id: str
    resource_version: str | None = None

    def __post_init__(self) -> None:
        """Require a resolved resource identity."""
        _require_nonblank(value=self.resource_kind, field="Resource kind")
        _require_nonblank(value=self.resource_id, field="Resource ID")
        if self.resource_version is not None:
            _require_nonblank(value=self.resource_version, field="Resource version")


class IdempotencyRepository(Protocol, metaclass=ABCMeta):
    """Persist durable invocation identity and fence its state transitions."""

    @abstractmethod
    async def claim(self, *, invocation: Invocation, owner: str) -> Lease | OperationOutcome:
        """Claim an available invocation, or replay its exact completed outcome."""

    @abstractmethod
    async def complete(
        self, *, invocation: Invocation, lease: Lease, outcome: OperationOutcome
    ) -> None:
        """Store the outcome under the current, unexpired lease."""

    @abstractmethod
    async def renew(self, *, invocation: Invocation, lease: Lease) -> Lease:
        """Extend the current lease and invalidate its previous snapshot."""

    @abstractmethod
    async def release(self, *, invocation: Invocation, lease: Lease) -> None:
        """Release commit authority while preserving the original request identity."""


class TransactionManager(Protocol, metaclass=ABCMeta):
    """Complete one transaction over a clean, operation-local resource."""

    @abstractmethod
    def begin(self) -> AbstractAsyncContextManager[None]:
        """Commit on successful exit and roll back on a failure before commit."""


class AuditRepository(Protocol, metaclass=ABCMeta):
    """Append and inspect detached, attributed events."""

    @abstractmethod
    async def append(self, *, record: AuditRecord) -> None:
        """Include an immutable event in the operation's transaction."""

    @abstractmethod
    async def list(
        self,
        *,
        project_id: ProjectId,
        model_id: ModelId | None,
        limit: int,
        cursor: PageCursor | None,
    ) -> Page[AuditRecord]:
        """List a stable snapshot of the project or model history."""


class WorkspaceRevisions(Protocol, metaclass=ABCMeta):
    """Read and advance the optimistic concurrency guard for a model."""

    @abstractmethod
    async def revision(self, *, scope: ModelScope) -> int:
        """Load the current revision for the exact model scope."""

    @abstractmethod
    async def advance(self, *, scope: ModelScope, expected_revision: int) -> None:
        """Advance exactly once if the current revision matches."""


class Transaction(TransactionManager, Protocol, metaclass=ABCMeta):
    """Bound repository bundle used by operation composition."""

    @property
    @abstractmethod
    def operations(self) -> IdempotencyRepository:
        """Return the idempotency repository sharing this operation's transaction."""

    @property
    @abstractmethod
    def audit(self) -> AuditRepository:
        """Return the audit repository sharing this operation's transaction."""

    @property
    @abstractmethod
    def revisions(self) -> WorkspaceRevisions:
        """Return the workspace revision guard sharing this operation's transaction."""


class UnitOfWorkFactory[T: Transaction](Protocol, metaclass=ABCMeta):
    """Acquire the collaborators for one operation without starting its transaction."""

    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[T]:
        """Return a context that releases the acquired resources on every exit."""
