# Direct injection and one atomic transaction

Read this for application services, database adapters and resource composition.
[State and persistence](../../../../ARCHITECTURE.md#state-and-persistence) owns the
transaction and resource boundaries. Read the owning Python ports for exact signatures.

## Keep the domain transition visible

This planned internal write records a new verified source revision after acquisition,
hashing and validation. It assumes a migrated `Source` whose `register_revision()`
validates and advances the source in place. The public ingestion workflow also
handles unchanged-content reuse and acquisition failures.

The SDK constructs the invocation and binds the canonical command, actor, reason
and expected source version to the registered operation and retry key. Each type
below has its own file.

`register_revision_command.py`

```python
from dataclasses import dataclass

from domain_kernel.sources.domain.models import SourceRevision


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
```

`register_revision.py`

```python
from abc import abstractmethod
from typing import Protocol

from domain_kernel._shared.application.persistence import Invocation
from domain_kernel.sources.domain.models import SourceRevision

from .register_revision_command import RegisterRevisionCommand


class RegisterRevision(Protocol):
    @abstractmethod
    async def register_revision(
        self, *, command: RegisterRevisionCommand, invocation: Invocation
    ) -> SourceRevision: ...
```

`revision_audit_factory.py`

```python
from abc import abstractmethod
from typing import Protocol

from domain_kernel._shared.application.persistence import Invocation
from domain_kernel._shared.domain.audit import AuditRecord
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.sources.domain.models import Source, SourceRevision


class RevisionAuditFactory(Protocol):
    @abstractmethod
    def source_hash(self, *, source: Source) -> ContentHash: ...

    @abstractmethod
    def create(
        self,
        *,
        invocation: Invocation,
        before_hash: ContentHash,
        after_hash: ContentHash,
        revision: SourceRevision,
        reason: str,
    ) -> AuditRecord: ...
```

The audit factory builds records from actual effect hashes and captured attribution.
Its implementation receives clocks and ID factories. The service captures the
before hash before calling the mutating method.

`register_revision_service.py`

```python
from typing import override

from domain_kernel._shared.application.persistence import (
    AuditRepository,
    IdempotencyRepository,
    Invocation,
    OperationOutcome,
    TransactionManager,
)
from domain_kernel.shared.errors import StaleStateError
from domain_kernel.sources.application.ports import SourceRepository
from domain_kernel.sources.domain.models import SourceRevision

from .register_revision import RegisterRevision
from .register_revision_command import RegisterRevisionCommand
from .revision_audit_factory import RevisionAuditFactory


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
    async def register_revision(
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
                stored = await self._sources.revision(
                    project_id=revision.project_id,
                    source_id=revision.source_id,
                    revision_id=revision.revision_id,
                )
                if stored is None:
                    raise RuntimeError("The stored revision outcome has no revision")
                return stored

            source = await self._sources.get(
                project_id=revision.project_id,
                source_id=revision.source_id,
            )
            if source.project_id != revision.project_id or source.id != revision.source_id:
                raise RuntimeError("The source adapter returned the wrong identity")
            expected_version = source.version
            if expected_version != command.expected_source_version:
                raise StaleStateError(message="Reload the source before adding this revision")

            before_hash = self._audit_records.source_hash(source=source)
            source.register_revision(revision=revision)

            await self._sources.add_revision(revision=revision)
            await self._sources.save(source=source, expected_version=expected_version)
            await self._audit.append(
                record=self._audit_records.create(
                    invocation=invocation,
                    before_hash=before_hash,
                    after_hash=self._audit_records.source_hash(source=source),
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

Register the illustrative `source_revision` codec key with the internal
operation-result mechanism. Matching retries replay before the observed-version
check. Claim and complete enforce the existing lease contract. Recover lost commit
acknowledgements with the original retry key. A return inside `async with` still
waits for context exit.

For publication preparation, save the complete blocked snapshot and outcome, exit
the transaction successfully, then raise `PublicationBlockedError`. Raising inside
the transaction would roll back the diagnostics.

## Compose narrow collaborators over one session

This factory belongs at the composition boundary. The built-in resource factory
owns its operation-local engine and session. A provider borrowing a host-owned pool
leaves the pool open. Long-lived client services hold factories and compose a new
session-bound service for each operation.

`revision_committers.py`

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from domain_kernel._shared.application.persistence import UnitOfWorkFactory
from domain_kernel.sources.application.ports import SourceTransaction

from .register_revision import RegisterRevision
from .register_revision_service import RegisterRevisionService
from .revision_audit_factory import RevisionAuditFactory


class RevisionCommitters:
    @staticmethod
    @asynccontextmanager
    async def open(
        *,
        resources: UnitOfWorkFactory[SourceTransaction],
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

Only composition reads the bundle properties. Entering the resource context acquires
the session. `begin()` owns the transaction and rejects a session with an active
transaction. Discard operation-local entities and session-bound state after a
failure.

## Map rows without leaking the ORM

This planned adapter sketch uses the existing SQLite mapping. The application
declares the lookup port in its own module. Move the row to `source_row.py` when
splitting the adapter and preserve its constraints. A full repository implements
all the operations it advertises.

`find_source.py`

```python
from abc import abstractmethod
from typing import Protocol

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.models import Source


class FindSource(Protocol):
    @abstractmethod
    async def find(self, *, project_id: ProjectId, source_id: SourceId) -> Source | None: ...
```

`sqlalchemy_source_reader.py`

```python
from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.sources.application.find_source import FindSource
from domain_kernel.sources.domain.identifiers.source_id import SourceId
from domain_kernel.sources.domain.models import Source

from .source_row import SourceRow


class SqlAlchemySourceReader(FindSource):
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    @override
    async def find(self, *, project_id: ProjectId, source_id: SourceId) -> Source | None:
        statement = select(SourceRow).where(
            SourceRow.project_id == project_id.value,
            SourceRow.identity == source_id.value,
        )
        result = await self._session.execute(statement=statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return Source(
            id=SourceId(value=row.identity),
            project_id=ProjectId(value=row.project_id),
            name=row.name,
            display_name=row.display_name,
            version=row.version,
        )
```

Keep typed queries and conversions in infrastructure. Use explicit or eager loads
and return detached results. Session expiry settings still allow lazy relationship
reads on ORM rows. Use `NullPool` for default operation-scoped engines, await
session closure and engine disposal, and preserve cleanup on cancellation. SQLite
requires correct transaction control, foreign keys per connection and bounded
concurrency.

Use the [SQLAlchemy async guidance](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html)
and selected dialect documentation during implementation. Follow the repository's
dependency and cooldown rules. Schema upgrades remain explicit.
