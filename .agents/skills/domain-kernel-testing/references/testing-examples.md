# Test the behavior at its real boundary

Read this when choosing assertions, writing fakes or adding persistence acceptance.
The [Testing entry point](../SKILL.md) owns TDD. Use the
[Python examples](../../domain-kernel-python-standards/references/services-and-persistence.md)
for the service and resource model.

## Pure domain rejection needs no database

Save the complete isolated example from
[domain and protocols](../../domain-kernel-python-standards/references/domain-and-protocols.md)
as `domain_example.py` in a temporary exercise directory. The following complete
`test_domain_example.py` imports that teaching module. These are exercises in behavior
and assertion quality, not additional production files or tests of Markdown wording.

```python
from __future__ import annotations

import pytest

from domain_kernel import DefinitionId
from domain_example import DefinitionNameIndex, DraftDefinitionName, DraftNameConflictError


def test_duplicate_name_rejection_preserves_existing_entries() -> None:
    original = DraftDefinitionName(
        definition_id=DefinitionId(value="definition-original"),
        name="recruitment-ai-system",
    )
    index = DefinitionNameIndex(entries=[original])

    with pytest.raises(expected_exception=DraftNameConflictError):
        index.add(
            entry=DraftDefinitionName(
                definition_id=DefinitionId(value="definition-other"),
                name="recruitment-ai-system",
            ),
        )

    assert index.entries == (original,)


def test_existing_identity_cannot_acquire_a_second_name() -> None:
    original = DraftDefinitionName(
        definition_id=DefinitionId(value="definition-original"),
        name="recruitment-ai-system",
    )
    index = DefinitionNameIndex(entries=[original])

    with pytest.raises(expected_exception=DraftNameConflictError):
        index.add(
            entry=DraftDefinitionName(
                definition_id=original.definition_id,
                name="high-risk-recruitment-ai-system",
            ),
        )

    assert index.entries == (original,)


def test_input_list_changes_do_not_mutate_the_index() -> None:
    original = DraftDefinitionName(
        definition_id=DefinitionId(value="definition-original"),
        name="recruitment-ai-system",
    )
    supplied = [original]
    index = DefinitionNameIndex(entries=supplied)
    supplied.clear()

    assert index.entries == (original,)


def test_valid_addition_preserves_the_previous_snapshot() -> None:
    index = DefinitionNameIndex()
    before = index.entries
    addition = DraftDefinitionName(
        definition_id=DefinitionId(value="definition-new"),
        name="instructions-for-use",
    )

    index.add(entry=addition)

    assert before == ()
    assert index.entries == (addition,)
```

These assertions distinguish a rejected operation from one that raised after changing
state. They also protect collection ownership and a successful transition. They say
nothing about database races or whether the complete SDK reserves the right names
on submission and during coordinated review. Those are separate tests of the owning
behavior.

## Use a small protocol fake to isolate orchestration

This narrow fake implements the internal `TransactionManager` protocol for service
tests. It records completion intent. Use a real adapter to observe storage rollback.

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import override

from domain_kernel.shared.application.persistence import TransactionManager


class RecordingTransactionManager(TransactionManager):
    def __init__(self) -> None:
        self.committed = False
        self.failed = False
        self.closed = False

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        try:
            yield
        except BaseException:
            self.failed = True
            raise
        else:
            self.committed = True
        finally:
            self.closed = True
```

In service tests, inject this alongside a failing audit adapter and real domain values,
invoke the service, and assert that the operation fails without reporting a completed
outcome. Do not use a test of this fake itself to claim service coverage or real rollback.
Fakes must implement the full protocol they advertise; use narrow ports rather than
casts, partial subclasses or broad mocks that silently accept unknown method names.

For the planned revision-commit service, cover these observable outcomes:

| Scenario | Service assertion |
|---|---|
| Valid new revision | The domain-produced source, exact revision, attributed audit and outcome reach the injected adapters |
| Matching completed retry | The stored revision is returned without a second domain transition or new audit; replay precedes a stale-version check |
| Changed intent under the same key | The idempotency conflict propagates; no revision/save/audit occurs |
| Wrong loaded source scope or identity | Reject before applying the domain transition or writing anything |
| Stale source version | Reject before mutation; no successful outcome |
| Save, audit or completion fails | Propagate failure; transaction success is not reported |
| Commit acknowledgement is uncertain | Preserve original invocation/recovery identity; never invent a fresh key or assume rollback |

Do not assert every incidental call or message text. Assert scope, versions, actual
effects and ordering only where they protect the intended guarantee.

## Prove atomicity with the real adapter

DK-003 and DK-039 own these integration tests. Use isolated file-backed SQLite and a
disposable PostgreSQL database, each running the real repository mappings and schema.
In-memory SQLite alone cannot establish cross-connection locking or restart behavior.
Inject a failure after the state write but before audit completion; after the failed
operation closes, inspect state through a fresh session. State, revision, audit and
idempotency outcome must all remain at their previous committed values.

| Scenario | Required database evidence |
|---|---|
| Concurrent identical commands | One durable outcome; matching retry returns it without duplicate effects |
| Concurrent conflicting commands | Unique/CAS constraints reject the loser without partial committed effects |
| Concurrent operations | Separate sessions, with each operation's adapters sharing its own session |
| Foreign-key violation | Rejected on every newly opened SQLite connection, not just the schema-creation connection |
| Context ownership | Exactly one transaction completion; nested/active transaction entry is rejected |
| Detached inspection | Results remain usable after closure without further SQL or lazy loading |
| Cancellation before/during/after commit | Owned resources close; observed committed state and recovery agree without assuming cancellation reversed a write |
| Blocked publication preparation | Diagnostics and its outcome remain retrievable after the documented exception |
| Injected host pool | Borrowed connections return, but the SDK never closes the host-owned pool |

Use events/barriers rather than sleeps to arrange races. A real adapter failure test
can substitute one boundary to force an error while keeping the actual database
transaction under test. Distinguish that from an entirely mocked database. Do not
weaken an assertion to accommodate incomplete schema, cleanup or cancellation logic.

Run the shared contract suite for each implemented database. Missing PostgreSQL
provisioning is an unavailable check, not evidence that SQLite qualifies PostgreSQL.
Keep owned resources and teardown explicit, and use the existing integration marker.

## Keep notebook and implementation evidence separate

A notebook interaction can prove that a preview explains rejection and preserves its
experiment branch. It cannot prove that the SDK extracted a grounded definition or
committed anything. Record preview and SDK implementation status separately in the
existing coverage ledger. Replace an owned mock only after the real operation and
its acceptance tests work, then verify the saved reading experience and live journey.
