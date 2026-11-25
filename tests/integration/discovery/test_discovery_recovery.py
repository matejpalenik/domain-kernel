"""Recover the exact discovery run after failure, cancellation or process exit."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, final

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DiscoveryProgress,
    IdempotencyConflictError,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    RunStatus,
    SourceId,
    SourceRevisionId,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel._database import SQLiteSettings, SQLiteUnitOfWorkFactory
from tests.support.discovery.create_discovery_workspace import (
    DISCOVERY_STATEMENT,
    create_discovery_workspace,
)
from tests.support.discovery.v23_gateway import V23Gateway

if TYPE_CHECKING:
    from domain_kernel import DiscoveryRunId
    from tests.support.persistence.database_backend import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


_CRASH_EXIT = 37


async def test_discovery_reopens_and_resumes_the_captured_request(
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = V23Gateway(malformed=True)
    project = await Client(
        config=database_backend.config.model_copy(update={"model_gateway": gateway}),
    ).create_project(actor="editor", name="recruitment")
    received = await project.ingest_source(
        actor="editor",
        name="application-reference",
        source=Statement(
            text=DISCOVERY_STATEMENT,
            speaker=Person(id=PersonId(value="owner"), name="Aria", role="Application owner"),
            context="Separate application lookup codes from provision identities.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="editor",
        name="review",
        kind=ModelKind.PROPOSED,
        description="Review an application-owned locator.",
    )
    failed = await model.discover(
        actor="editor",
        sources=(received.revision,),
        additional_instructions="This should not replace the override.",
        prompt_override="Capture the sourced application code.",
        idempotency_key="recruitment-discovery-request",
    )
    assert failed.status is RunStatus.FAILED
    assert failed.failures
    failure = failed.failures[0]
    assert failure.message == failure.issue.message
    assert failure.code == failure.issue.code
    assert failure.severity is failure.issue.severity
    assert not (await model.list_review_cases(run_id=failed.id)).items
    with pytest.raises(IdempotencyConflictError):
        _ = await model.discover(
            actor="editor",
            sources=(received.revision,),
            additional_instructions="Changed ignored text.",
            prompt_override="Capture the sourced application code.",
            idempotency_key="recruitment-discovery-request",
        )
    monkeypatch.setattr(
        "domain_kernel.discovery.application.structured_output.response_schema",
        lambda: "A later deployment supplies a different schema.",
    )

    fresh_gateway = V23Gateway()
    restored = await Client(
        config=database_backend.config.model_copy(update={"model_gateway": fresh_gateway}),
    ).get_project(name="recruitment")
    current = await restored.get_model(name="review")
    assert await current.get_discovery_run(run_id=failed.id) == failed
    completed = await current.resume_discovery(
        actor="editor",
        run_id=failed.id,
        idempotency_key="recover-recruitment-discovery",
    )
    assert completed.id == failed.id
    assert completed.status is RunStatus.NEEDS_REVIEW
    assert completed.prompt == failed.prompt
    assert completed.failures == ()
    (first, second) = (gateway.requests[0], fresh_gateway.requests[0])
    assert first.instructions == second.instructions
    frame = TypeAdapter(dict[str, object]).validate_json(second.context_json or "{}")
    assert frame["modeling_instructions"] == "Capture the sourced application code."
    assert first.response_schema_json == second.response_schema_json
    assert first.inputs == second.inputs
    cases = tuple(
        [case async for case in current.iter_review_cases(run_id=completed.id, page_size=1)]
    )
    assert len(cases) == 1
    assert (await current.list_discovery_runs()).items == (completed,)
    assert (
        await current.resume_discovery(
            actor="editor",
            run_id=completed.id,
            idempotency_key="recover-recruitment-discovery",
        )
        == completed
    )
    assert [request.provider_stage for request in fresh_gateway.requests] == [
        "schema-compact-draft",
        "schema-compact-repair",
    ]


@final
class _InterruptedGateway:
    supports_schema_discovery = True

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        del request
        self.started.set()
        await asyncio.Future[None]()
        raise AssertionError("The first worker was deliberately interrupted.")


async def test_cancelled_discovery_recovers_the_same_run_and_queue(tmp_path: Path) -> None:
    gateway = _InterruptedGateway()
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway),
    ).create_project(actor="editor", name="cancelled")
    capture = await project.ingest_source(
        actor="editor",
        name="captured",
        source=Statement(
            text=DISCOVERY_STATEMENT,
            speaker=Person(id=PersonId(value="owner"), name="Aria", role="Application owner"),
            context="Review the provision reference.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="editor",
        name="work",
        kind=ModelKind.PROPOSED,
        description="Review source meanings.",
    )
    ids: list[DiscoveryRunId] = []

    def capture_progress(event: DiscoveryProgress) -> None:
        ids.append(event.run_id)

    worker = asyncio.create_task(
        model.discover(
            actor="editor",
            sources=[capture.revision],
            on_progress=capture_progress,
        )
    )
    _ = await asyncio.wait_for(gateway.started.wait(), timeout=5)
    _ = worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        _ = await worker
    (run_id,) = set(ids)
    offline = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(
        name=project.name
    )
    detached = await offline.get_model(name=model.info.name)
    cancelled = await detached.get_discovery_run(run_id=run_id)
    assert cancelled.status is RunStatus.CANCELLED
    assert not (await detached.list_review_cases(run_id=run_id)).items
    fresh = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=V23Gateway()),
    ).get_project(name=project.name)
    recovered = await (await fresh.get_model(name=model.info.name)).resume_discovery(
        actor="recovery-operator",
        run_id=run_id,
    )
    assert recovered.id == run_id
    assert recovered.prompt == cancelled.prompt
    assert recovered.status is RunStatus.NEEDS_REVIEW
    (pending,) = (await detached.list_review_cases(run_id=run_id)).items
    before = await detached.compile(actor="editor")
    assert before.content.definitions == ()
    decision = Accept(reason="Keep the evidenced application code.")
    _ = await detached.preview_changes(case=pending, decision=decision)
    _ = await detached.decide_review(actor="reviewer", case=pending, decision=decision)
    after = await detached.compile(actor="editor")
    (approved,) = after.content.definitions
    assert approved.id == pending.definitions[0].id
    changes = await detached.diff(before=before, after=after)
    assert [item.id for change in changes.changes for item in change.after] == [approved.id]


async def _crash_in_discovery(*, root: str, source: str, revision: str, checkpoint: str) -> None:
    class CrashingGateway:
        supports_schema_discovery: bool = True

        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if checkpoint == "inference":
                os._exit(_CRASH_EXIT)
            return await V23Gateway().generate(request=request)

    reconciling = 0

    def stop_after_checkpoint(event: DiscoveryProgress) -> None:
        nonlocal reconciling
        if event.stage is RunStatus.RECONCILING:
            reconciling += 1
            expected = "draft" if reconciling == 1 else "aligned"
            if checkpoint == expected:
                os._exit(_CRASH_EXIT)

    client = Client(
        config=ClientConfiguration(base_dir=Path(root), model_gateway=CrashingGateway())
    )
    project = await client.get_project(name="recruitment")
    model = await project.get_model(name="locators")
    captured = await project.get_source_revision(
        source_id=SourceId(value=source), revision_id=SourceRevisionId(value=revision)
    )
    _ = await model.discover(
        actor="editor",
        sources=(captured,),
        prompt_override="Capture the exact lookup code.",
        idempotency_key="interrupted-process",
        on_progress=stop_after_checkpoint,
    )


@pytest.mark.parametrize("checkpoint", ["inference", "draft", "aligned"])
async def test_discovery_recovers_after_a_process_dies_at_a_checkpoint(
    tmp_path: Path, checkpoint: str
) -> None:
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=None)
    entrypoint = _crash_in_discovery.__name__
    script = f"""
import asyncio
import json
import sys
from tests.integration.discovery.test_discovery_recovery import {entrypoint}

asyncio.run({entrypoint}(
    root=sys.argv[1], source=sys.argv[2], revision=sys.argv[3], checkpoint=sys.argv[4]
))
"""
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(tmp_path),
        revision.source_id.value,
        revision.revision_id.value,
        checkpoint,
    )
    try:
        assert await asyncio.wait_for(worker.wait(), timeout=20) == _CRASH_EXIT
    finally:
        if worker.returncode is None:
            worker.kill()
            _ = await worker.wait()
    (interrupted,) = (await model.list_discovery_runs()).items
    expected_status = RunStatus.EXTRACTING if checkpoint == "inference" else RunStatus.RECONCILING
    assert interrupted.status is expected_status
    prior_cases = (await model.list_review_cases(run_id=interrupted.id)).items
    assert len(prior_cases) == (1 if checkpoint == "aligned" else 0)

    fresh_gateway = V23Gateway()
    future = datetime.now(tz=UTC) + timedelta(minutes=2)
    transactions = SQLiteUnitOfWorkFactory(
        settings=SQLiteSettings(path=tmp_path / ".domain-kernel/state.sqlite3"),
        clock=lambda: future,
    )
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=fresh_gateway),
        integrations=ClientIntegrations(transactions=transactions),
    )
    reopened = await (await client.get_project(name="recruitment")).get_model(name="locators")
    recovered = await reopened.resume_discovery(actor="operator", run_id=interrupted.id)
    assert recovered.status is RunStatus.NEEDS_REVIEW
    assert recovered.prompt == interrupted.prompt
    (case,) = (await reopened.list_review_cases(run_id=recovered.id)).items
    if prior_cases:
        assert (case,) == prior_cases
    if checkpoint == "aligned":
        assert fresh_gateway.requests == []
    else:
        drafting, review = fresh_gateway.requests
        frame = TypeAdapter(dict[str, object]).validate_json(drafting.context_json or "{}")
        assert frame["modeling_instructions"] == "Capture the exact lookup code."
        assert review.provider_stage == "schema-compact-repair"
