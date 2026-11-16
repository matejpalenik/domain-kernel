# Direct injection and one atomic transaction

Read this for application services, database adapters and resource composition.
[State and persistence](../../../../ARCHITECTURE.md#state-and-persistence) and the
[internal contracts](../../../../INTERFACES.md) are authoritative. The following
planned internal example uses those ports. It is not implemented SDK functionality
or a new public ingestion method. Its small command/capability/audit-factory types
explain the private new-revision commit stage; they are not new exported contracts.

## Keep the domain transition visible

Source acquisition, hashing and validation have already finished. This stage records
a genuinely new verified revision. The public ingestion workflow also handles
unchanged-content reuse and acquisition failures; do not replace it with this stage.
Its SDK-owned invocation binds the canonical command, actor, reason and expected
source version to the registered operation and retry key. It is never trusted input
supplied directly by a downstream caller.

```python
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol, override

from domain_kernel._shared.application.persistence import (
    AuditRepository,
    IdempotencyRepository,
    Invocation,
    OperationOutcome,
    TransactionManager,
)
from domain_kernel._shared.domain.audit import AuditRecord
from domain_kernel._shared.domain.contracts import SourceRevision
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.sources.application.ports import SourceRepository, SourceRevisionReference
from domain_kernel.sources.domain.models import Source


@dataclass(frozen=True, kw_only=True)
class RegisterRevisionCommand:
    revision: SourceRevision
    expected_source_version: int
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.revision, SourceRevision):
            raise TypeError("revision must be a verified SourceRevision")
        if type(self.expected_source_version) is not int or self.expected_source_version < 0:
            raise ValueError("expected_source_version must be a nonnegative integer")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be nonblank")


class RegisterRevision(Protocol):
    @abstractmethod
    async def execute(
        self, *, command: RegisterRevisionCommand, invocation: Invocation
    ) -> SourceRevision: ...


class RevisionAuditFactory(Protocol):
    @abstractmethod
    def create(
        self,
        *,
        invocation: Invocation,
        before: Source,
        after: Source,
        revision: SourceRevision,
        reason: str,
    ) -> AuditRecord: ...

    # Build the ordinary AuditRecord with captured actor, generated ID/time,
    # actual before/after resource hashes, source revision and parent attribution.
    # Inject clocks/ID factories into this helper; no database/provider access.


class RegisterRevisionService(RegisterRevision):
    def __init__(
        self,
        *,
        sources: SourceRepository,
        audit: AuditRepository,
        operations: IdempotencyRepository,
        transactions: TransactionManager,
        audit_records: RevisionAuditFactory,
        owner: str,
    ) -> None:
        self._sources = sources
        self._audit = audit
        self._operations = operations
        self._transactions = transactions
        self._audit_records = audit_records
        self._owner = owner

    @override
    async def execute(
        self, *, command: RegisterRevisionCommand, invocation: Invocation
    ) -> SourceRevision:
        revision = command.revision
        if invocation.project_id != revision.project_id or invocation.model_id is not None:
            raise RuntimeError("The internal invocation has the wrong source scope")

        async with self._transactions.begin():
            claim = await self._operations.claim(invocation=invocation, owner=self._owner)
            if isinstance(claim, OperationOutcome):
                if (
                    claim.resource_kind != "source_revision"
                    or claim.resource_id != revision.revision_id.value
                    or claim.resource_version is not None
                ):
                    raise RuntimeError("The stored revision outcome does not match its intent")
                return await self._sources.get_revision(
                    reference=SourceRevisionReference.from_revision(revision=revision),
                )

            source = await self._sources.get(
                project_id=revision.project_id,
                source_id=revision.source_id,
            )
            if source.project_id != revision.project_id or source.id != revision.source_id:
                raise RuntimeError("The source adapter returned the wrong identity")
            if source.version != command.expected_source_version:
                raise StaleStateError(message="Reload the source before adding this revision")

            changed = source.register_revision(revision=revision)

            await self._sources.add_revision(revision=revision)
            await self._sources.save(source=changed, expected_version=source.version)
            await self._audit.append(
                record=self._audit_records.create(
                    invocation=invocation,
                    before=source,
                    after=changed,
                    revision=revision,
                    reason=command.reason,
                ),
            )
            await self._operations.complete(
                invocation=invocation,
                lease=claim,
                outcome=OperationOutcome(
                    resource_kind="source_revision",
                    resource_id=revision.revision_id.value,
                    resource_version=None,
                ),
            )

        return revision
```

The `source_revision` outcome is an illustrative internal registered codec key,
not a new public discriminator. The implementation must register/validate it through
the existing operation-result mechanism. The invocation producer must include the
command's complete meaning in its hash; matching retries replay before checking a
now-stale source version. Claim/complete enforce the existing lease and fencing
contract. Never add a fresh retry key because commit acknowledgement was lost.

The domain method owns the revision transition. The service checks loaded identity
and observed version and the repository enforces the final CAS. Audit records actual
effects, not merely command intent. All writes share the transaction and no repository
commits independently. A return inside `async with` still waits for context exit.

For publication preparation, the pattern differs deliberately: save its complete
blocked snapshot and outcome, leave the transaction successfully, then raise
`PublicationBlockedError`. Raising inside the transaction would erase the diagnostics.

## Compose narrow collaborators over one session

The following block continues the preceding example module. The selected built-in
factory owns its operation-local engine/session. An injected provider may borrow
from a host-owned pool, but never closes that pool. Long-lived client services hold
factories, not these session-bound service instances.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from domain_kernel._shared.application.persistence import UnitOfWorkFactory
from domain_kernel.sources.application.ports import SourcesTransaction


@asynccontextmanager
async def open_revision_committer(
    *,
    resources: UnitOfWorkFactory[SourcesTransaction],
    audit_records: RevisionAuditFactory,
    owner: str,
) -> AsyncIterator[RegisterRevision]:
    async with resources() as bound:
        yield RegisterRevisionService(
            sources=bound.sources,
            audit=bound.audit,
            operations=bound.operations,
            transactions=bound,
            audit_records=audit_records,
            owner=owner,
        )
```

Only composition reads the bundle properties. The service sees the narrow
`TransactionManager` capability. Resource entry does not start a transaction;
`begin()` owns exactly one completion. Reject an already active session rather than
silently joining, nesting or retrying. Discard session-bound state after failure.

## Map rows without leaking the ORM

This standalone planned infrastructure fragment illustrates a scoped source read.
`SourceRowReader` is a narrow helper capability for the example, not the complete
`SourceRepository`. A real adapter must implement every repository operation it
advertises. Its authoritative schema and migrations also need the accepted uniqueness,
foreign-key and version constraints; this fragment is not a migration definition.

```python
from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.models import Source


class SourceRows(DeclarativeBase):
    pass


class SourceRow(SourceRows):
    __tablename__ = "source"

    project_id: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    display_name: Mapped[str]
    version: Mapped[int]


class SourceRowReader(Protocol):
    @abstractmethod
    async def find(self, *, project_id: ProjectId, source_id: SourceId) -> Source | None: ...


class SqlAlchemySourceReader(SourceRowReader):
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    @override
    async def find(self, *, project_id: ProjectId, source_id: SourceId) -> Source | None:
        statement = select(SourceRow).where(
            SourceRow.project_id == project_id.value,
            SourceRow.id == source_id.value,
        )
        result = await self._session.execute(statement=statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return Source(
            id=SourceId(value=row.id),
            project_id=ProjectId(value=row.project_id),
            name=row.name,
            display_name=row.display_name,
            version=row.version,
        )
```

The result has no session, ORM relationship or deferred column access. Keep typed
queries and mappers in infrastructure. Use eager/explicit loads and detached results;
`expire_on_commit=False` does not make an ORM object a domain value or prevent lazy
relationship reads. Use `NullPool` for default operation-scoped engines, await session
closure and engine disposal, and preserve cleanup on cancellation. A lost commit
acknowledgement remains uncertain even if cleanup succeeds. SQLite still needs
correct transaction control, foreign keys per connection and bounded concurrency.

Use [SQLAlchemy async guidance](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html)
and the selected dialect documentation during implementation. SQLAlchemy/aiosqlite
are added only with DK-003 and Psycopg with DK-039, using uv and the cooldown.
Schema upgrades remain explicit; do not add an automatic migration on client startup.
