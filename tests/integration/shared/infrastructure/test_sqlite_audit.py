"""Verify the audit, workspace revision and outcome boundary on a real file."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from domain_kernel import ContentHash, ModelId, ModelScope, ProjectId, StaleStateError
from domain_kernel._database import SchemaManager, SQLiteSettings, SQLiteUnitOfWorkFactory
from domain_kernel.shared.application.idempotency.invocation import Invocation
from domain_kernel.shared.application.idempotency.lease import Lease
from domain_kernel.shared.application.idempotency.operation_outcome import OperationOutcome
from domain_kernel.shared.domain.entities.artifact import Artifact
from domain_kernel.shared.domain.entities.audit_record import AuditRecord
from domain_kernel.shared.domain.enums.audit_action import AuditAction
from domain_kernel.shared.domain.enums.audit_outcome import AuditOutcome
from domain_kernel.shared.domain.value_objects.audit_resource import AuditResource
from domain_kernel.shared.identifiers.audit_id import AuditId

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_SCOPE = ModelScope(project_id=ProjectId(value="recruitment"), model_id=ModelId(value="observed"))
_HASH = ContentHash(value=f"sha256:{'a' * 64}")


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> SQLiteUnitOfWorkFactory:
    settings = SQLiteSettings(path=tmp_path / "state.sqlite3")
    await SchemaManager(settings=settings).initialize()
    with closing(sqlite3.connect(database=settings.path)) as connection, connection:
        _ = connection.execute(
            "INSERT INTO dk_project VALUES (?, ?, ?, ?)",
            ("recruitment", "recruitment", "Recruitment", "2026-11-16T00:00:00+00:00"),
        )
        _ = connection.execute(
            "INSERT INTO dk_model VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "recruitment",
                "observed",
                "observed",
                "Observed",
                "Scope",
                "observed",
                "2026-11-16T00:00:00+00:00",
                0,
            ),
        )
    return SQLiteUnitOfWorkFactory(settings=settings)


def _event(*, identity: str) -> AuditRecord:
    return AuditRecord(
        id=AuditId(value=identity),
        project_id=_SCOPE.project_id,
        model_id=_SCOPE.model_id,
        actor="editor",
        recorded_at=datetime(2026, 11, 16, tzinfo=UTC),
        action=AuditAction.DECIDE_REVIEW,
        outcome=AuditOutcome.SUCCEEDED,
        before=[AuditResource(resource_id=_SCOPE.model_id, revision=0, content_hash=_HASH)],
        after=[AuditResource(resource_id=_SCOPE.model_id, revision=1, content_hash=_HASH)],
        reason="The inspected shape retains its unit reference.",
    )


async def test_failed_audit_rolls_back_revision_and_replay_outcome(
    database: SQLiteUnitOfWorkFactory,
) -> None:
    original = _event(identity="recorded")
    invocation = Invocation.resolve(
        project_id=_SCOPE.project_id,
        model_id=_SCOPE.model_id,
        operation="decide_review",
        actor="editor",
        key="case-1",
        intent={"version": 1},
    )
    async with database() as transaction, transaction.begin():
        await transaction.audit.append(record=original)

    async def produce_duplicate_event() -> None:
        async with database() as transaction, transaction.begin():
            lease = await transaction.operations.claim(invocation=invocation, owner="reviewer")
            assert isinstance(lease, Lease)
            await transaction.revisions.advance(scope=_SCOPE, expected_revision=0)
            await transaction.operations.complete(
                invocation=invocation,
                lease=lease,
                outcome=OperationOutcome(resource_kind="decision", resource_id="rolled-back"),
            )
            await transaction.audit.append(record=original)

    with pytest.raises(IntegrityError):
        await produce_duplicate_event()

    async with database() as transaction, transaction.begin():
        assert await transaction.revisions.revision(scope=_SCOPE) == 0
        page = await transaction.audit.list(
            project_id=_SCOPE.project_id,
            model_id=_SCOPE.model_id,
            limit=10,
            cursor=None,
        )
        assert isinstance(
            await transaction.operations.claim(invocation=invocation, owner="retry"), Lease
        )
        await transaction.revisions.advance(scope=_SCOPE, expected_revision=0)
        with pytest.raises(StaleStateError):
            await transaction.revisions.advance(scope=_SCOPE, expected_revision=0)
    assert page.items == (original,)


async def test_audit_pages_preserve_history_and_bind_scope(
    database: SQLiteUnitOfWorkFactory,
) -> None:
    artifact = Artifact(
        project_id=_SCOPE.project_id,
        model_id=_SCOPE.model_id,
        key="recruitment.json",
        store="exports",
        content_hash=_HASH,
    )
    intent = replace(
        _event(identity="intent"),
        action=AuditAction.EXPORT,
        outcome=AuditOutcome.STARTED,
        before=[],
        after=[],
        requested_artifact=artifact,
    )
    verified = replace(
        intent,
        id=AuditId(value="complete"),
        parent_id=intent.id,
        outcome=AuditOutcome.SUCCEEDED,
        requested_artifact=None,
        after=[artifact],
    )
    async with database() as transaction, transaction.begin():
        await transaction.audit.append(record=intent)
        await transaction.audit.append(record=verified)

    async with database() as transaction, transaction.begin():
        first = await transaction.audit.list(
            project_id=_SCOPE.project_id,
            model_id=_SCOPE.model_id,
            limit=1,
            cursor=None,
        )
    assert first.items == (intent,)
    assert first.next_cursor is not None

    async with database() as transaction, transaction.begin():
        await transaction.audit.append(record=_event(identity="later"))

    async with database() as transaction, transaction.begin():
        with pytest.raises(ValueError, match="same audit history query"):
            _ = await transaction.audit.list(
                project_id=_SCOPE.project_id,
                model_id=None,
                limit=1,
                cursor=first.next_cursor,
            )
        second = await transaction.audit.list(
            project_id=_SCOPE.project_id,
            model_id=_SCOPE.model_id,
            limit=1,
            cursor=first.next_cursor,
        )
    assert second.items == (verified,)
    assert second.next_cursor is None


async def test_workspace_scope_foreign_keys_apply_on_every_connection(
    database: SQLiteUnitOfWorkFactory,
) -> None:
    missing_model = replace(
        _event(identity="bad-scope"),
        model_id=ModelId(value="missing"),
        before=[],
        after=[],
    )

    async def append_outside_scope() -> None:
        async with database() as transaction, transaction.begin():
            await transaction.audit.append(record=missing_model)

    for _attempt in range(2):
        with pytest.raises(IntegrityError):
            await append_outside_scope()
