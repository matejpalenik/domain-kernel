"""Exercise extraction, guarded replay and failure recovery with a detached gateway."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, final

import pytest
from pydantic import BaseModel, TypeAdapter

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ConceptDefinition,
    DefinitionStatus,
    DiscoveryProgress,
    IdempotencyConflictError,
    InferenceError,
    LangGraphDiscoveryGateway,
    LocalReplayGateway,
    MissingCapabilityError,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    RunStatus,
    SourceId,
    SourceRevisionId,
    StaleStateError,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel._database import SQLiteSettings, SQLiteUnitOfWorkFactory
from domain_kernel.discovery.application import aggregate_verification
from domain_kernel.discovery.application.claim_extraction import Verdicts
from domain_kernel.discovery.application.workflow import DiscoveryWorkflow

if TYPE_CHECKING:
    from domain_kernel import DiscoveryResult, DiscoveryRunId, Model, ModelGateway, SourceRevision
    from domain_kernel.discovery.application.workflow import (
        _Worker,  # pyright: ignore[reportPrivateUsage] -- Capture the caller's lease and version at the gate.
    )
    from domain_kernel.discovery.domain.models import SourceCheckpoint
    from domain_kernel.reconciliation.domain.models import Alignment
    from domain_kernel.shared.errors import DomainKernelError
    from tests.integration.conftest import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_RESPONSE = (
    '{"concepts":[{"name":"application-code","display_name":"Application code",'
    '"meaning":"A lookup code for a reviewed provision.","citations":[1],"confidence":null}],'
    '"relationships":[]}'
)
_TEXT = "This code locates a provision in our recruitment application."
_CRASH_EXIT = 37


@final
class _Gateway:
    def __init__(self, *, result: str = _RESPONSE, failures: int = 0) -> None:
        self.result = result
        self.failures = failures
        self.requests: list[ModelRequest] = []

    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) <= self.failures:
            raise InferenceError(retryable=True)
        return ModelResponse(
            output_json=self.result,
            model_id="stored/test-model",
            input_tokens=16,
            output_tokens=24,
        )


@final
class _V23Gateway:
    supports_schema_discovery = True

    def __init__(self, *, malformed: bool = False) -> None:
        self.malformed = malformed
        self.requests: list[ModelRequest] = []

    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.malformed:
            return ModelResponse(output_json='{"concepts":', model_id="test/v23")
        if request.provider_stage == "schema-compact-draft":
            body: dict[str, object] = {
                "concepts": [
                    {
                        "name": "application-code",
                        "display_name": "Application code",
                        "meaning": "A lookup code for a provision.",
                        "question_ids": ["purpose"],
                        "witnesses": ["E1.1"],
                        "modality": "descriptive",
                        "qualifiers": [],
                        "applicability": "This application.",
                    }
                ],
                "relationships": [],
                "questions": [],
                "unresolved_facets": [],
            }
        else:
            assert request.provider_stage == "schema-compact-repair"
            body = {
                "upsert": {"concepts": [], "relationships": [], "questions": []},
                "drop": [],
                "label_edits": [],
                "label_flags": [],
                "checks": [
                    {
                        "facet_id": 1,
                        "example": _TEXT,
                        "contrast": None,
                        "status": "supported",
                        "concepts": ["application-code"],
                        "links": [],
                        "witnesses": ["E1.1"],
                        "reason": "The source explicitly describes a lookup code.",
                    }
                ],
            }
        return ModelResponse(output_json=json.dumps(body), model_id="test/v23")


async def _workspace(
    *,
    path: Path,
    gateway: ModelGateway | None,
) -> tuple[Model, SourceRevision]:
    project = await Client(
        config=ClientConfiguration(
            base_dir=path,
            model_gateway=gateway,
        )
    ).create_project(actor="editor", name="recruitment")
    statement = await project.ingest_source(
        actor="editor",
        name="application-code-interview",
        source=Statement(
            text=_TEXT,
            speaker=Person(id=PersonId(value="developer"), name="Ari", role="Developer"),
            context="Application codes",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="editor",
        name="locators",
        kind=ModelKind.PROPOSED,
        description="The application needs internal lookup codes.",
    )
    return model, statement.revision


class _Selection(TypedDict):
    actor: str
    idempotency_key: str
    additional_instructions: str
    prompt_override: str


async def test_extraction_uses_the_same_gateway_and_reopens_exact_draft(tmp_path: Path) -> None:
    gateway = _Gateway(failures=1)
    model, revision = await _workspace(path=tmp_path, gateway=gateway)
    arguments: _Selection = {
        "actor": "editor",
        "idempotency_key": "first-extraction",
        "additional_instructions": "Include the lookup code.",
        "prompt_override": "Draft application-owned meanings.",
    }
    draft = await model.extract_proposals(source_revisions=[revision], **arguments)
    first, retried = gateway.requests
    assert retried == first
    assert first.instructions == "Draft application-owned meanings."
    assert _TEXT not in first.instructions
    assert first.inputs[0].text == _TEXT
    assert "internal lookup codes" in (first.context_json or "")
    (proposal,) = draft.proposals
    assert type(proposal.definition.body) is ConceptDefinition
    assert proposal.evidence[0].source == revision
    assert proposal.definition.status is DefinitionStatus.PROPOSED
    assert draft.provenance.provider_model_id == "stored/test-model"
    assert draft.provenance.input_tokens is not None
    assert not (await model.list_review_cases()).items
    assert not (await model.list_discovery_runs()).items

    reopened = await Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            model_gateway=gateway,
        )
    ).get_project(name="recruitment")
    again = await reopened.get_model(name="locators")
    assert await again.extract_proposals(source_revisions=[revision], **arguments) == draft
    assert gateway.requests == [first, retried]
    with pytest.raises(IdempotencyConflictError):
        _ = await again.extract_proposals(
            source_revisions=[revision],
            actor="editor",
            idempotency_key="first-extraction",
            prompt_override="Draft application-owned meanings.",
            additional_instructions="Changed even though the override wins.",
        )
    with pytest.raises(ValueError, match="nonblank"):
        _ = await again.extract_proposals(
            source_revisions=[revision],
            actor="editor",
            prompt_override=" ",
        )
    assert gateway.requests == [first, retried]


@pytest.mark.parametrize(
    "output",
    [
        '{"concepts":',
        _RESPONSE.replace('"citations":[1]', '"citations":[]'),
        _RESPONSE.replace('"citations":[1]', '"citations":[2]'),
        _RESPONSE.replace('"confidence":null', '"confidence":null,"approved":true'),
    ],
)
async def test_malformed_responses_do_not_become_drafts(tmp_path: Path, output: str) -> None:
    gateway = _Gateway(result=output)
    model, revision = await _workspace(path=tmp_path, gateway=gateway)
    with pytest.raises(InferenceError, match="Review provider output"):
        _ = await model.extract_proposals(
            actor="editor",
            source_revisions=[revision],
            idempotency_key="recover",
        )
    assert len(gateway.requests) == 1
    gateway.result = _RESPONSE
    recovered = await model.extract_proposals(
        actor="editor",
        source_revisions=[revision],
        idempotency_key="recover",
    )
    assert len(recovered.proposals) == 1


async def test_a_configured_gateway_is_required_only_for_extraction(tmp_path: Path) -> None:
    model, revision = await _workspace(path=tmp_path, gateway=None)
    with pytest.raises(MissingCapabilityError, match="model gateway"):
        _ = await model.extract_proposals(actor="editor", source_revisions=[revision])
    case = await model.propose_definition(
        actor="editor",
        name="manual-code",
        meaning="An authored code.",
        body=ConceptDefinition(),
        reason="Review independently.",
    )
    assert case.definitions


@pytest.mark.parametrize(
    ("output", "code", "path"),
    [
        (_RESPONSE.replace("[1]", "[2]"), "invalid_citation", ("concepts", 0, "citations", 0)),
        (
            _RESPONSE.replace("null", '"secret-value"'),
            "invalid_confidence",
            ("concepts", 0, "confidence"),
        ),
        (_RESPONSE.replace('"name":', '"name2":'), "invalid_shape", ("concepts", 0, "name")),
        (
            _RESPONSE.replace(
                '"relationships":[]',
                '"relationships":[{"name":"links","source":"application-code","target":"secret-value","display_name":"Link","meaning":"Link","citations":[1],"confidence":null}]',
            ),
            "unknown_endpoint",
            ("relationships", 0, "target"),
        ),
    ],
)
async def test_standalone_extraction_reports_the_invalid_field(
    tmp_path: Path, output: str, code: str, path: tuple[str | int, ...]
) -> None:
    model, revision = await _workspace(path=tmp_path, gateway=_Gateway(result=output))
    with pytest.raises(InferenceError) as caught:
        _ = await model.extract_proposals(source_revisions=[revision], actor="reviewer")
    issue = caught.value.issue
    assert issue is not None
    assert issue.path[-len(path) :] == path
    assert issue.code == code
    assert "secret-value" not in issue.message


async def test_discovery_reopens_and_resumes_the_captured_request(
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _V23Gateway(malformed=True)
    project = await Client(
        config=database_backend.config.model_copy(update={"model_gateway": gateway}),
    ).create_project(actor="editor", name="recruitment")
    received = await project.ingest_source(
        actor="editor",
        name="application-reference",
        source=Statement(
            text=_TEXT,
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

    fresh_gateway = _V23Gateway()
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
            text=_TEXT,
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
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=_V23Gateway()),
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
            return await _V23Gateway().generate(request=request)

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
    model, revision = await _workspace(path=tmp_path, gateway=None)
    entrypoint = _crash_in_discovery.__name__
    script = f"""
import asyncio
import json
import sys
from tests.integration.test_proposal_extraction import {entrypoint}

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

    fresh_gateway = _V23Gateway()
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


async def test_expired_discovery_worker_cannot_commit_after_takeover(tmp_path: Path) -> None:
    _, revision = await _workspace(path=tmp_path, gateway=None)
    now = datetime.now(tz=UTC)
    started, finish = asyncio.Event(), asyncio.Event()

    class SlowGateway:
        supports_schema_discovery: bool = True

        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            started.set()
            _ = await finish.wait()
            return await _V23Gateway().generate(request=request)

    def clock() -> datetime:
        return now

    settings = SQLiteSettings(path=tmp_path / ".domain-kernel/state.sqlite3")
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=SlowGateway()),
        integrations=ClientIntegrations(
            transactions=SQLiteUnitOfWorkFactory(settings=settings, clock=clock)
        ),
    )
    worker_model = await (await client.get_project(name="recruitment")).get_model(name="locators")
    stale = asyncio.create_task(worker_model.discover(actor="editor", sources=(revision,)))
    try:
        _ = await asyncio.wait_for(started.wait(), timeout=5)
        (interrupted,) = (await worker_model.list_discovery_runs()).items
        now += timedelta(minutes=2)
        successor = Client(
            config=ClientConfiguration(base_dir=tmp_path, model_gateway=_V23Gateway()),
            integrations=ClientIntegrations(
                transactions=SQLiteUnitOfWorkFactory(settings=settings, clock=clock)
            ),
        )
        reopened = await (await successor.get_project(name="recruitment")).get_model(
            name="locators"
        )
        recovered = await reopened.resume_discovery(actor="operator", run_id=interrupted.id)
        finish.set()
        with pytest.raises(StaleStateError):
            _ = await asyncio.wait_for(stale, timeout=5)
        assert recovered.status is RunStatus.NEEDS_REVIEW
        assert await reopened.get_discovery_run(run_id=recovered.id) == recovered
        assert len((await reopened.list_review_cases(run_id=recovered.id)).items) == 1
    finally:
        if not stale.done():
            _ = stale.cancel()
            _ = await asyncio.gather(stale, return_exceptions=True)


@final
class _DiscoveryTakeoverGates:
    """Pause each caller just before its selected checkpoint transaction."""

    def __init__(self, *, timeout: int) -> None:
        self._timeout = timeout
        self.original_waiting = asyncio.Event()
        self.resume_waiting = asyncio.Event()
        self.release_original = asyncio.Event()
        self.release_resume = asyncio.Event()
        self.checkpoints: dict[str, tuple[str, int]] = {}
        self.original: asyncio.Task[DiscoveryResult] | None = None
        self.resumed: asyncio.Task[DiscoveryResult] | None = None

    def install(self, *, monkeypatch: pytest.MonkeyPatch) -> None:
        # Only control entry timing. Both callers still execute the real transaction.
        checkpoint = DiscoveryWorkflow._checkpoint  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

        async def pause_checkpoint(  # noqa: PLR0913 - Forward the real checkpoint arguments unchanged.
            workflow: DiscoveryWorkflow,
            *,
            worker: _Worker,
            status: RunStatus,
            task: SourceCheckpoint | None = None,
            report: bool = True,
            consolidated: Alignment | None = None,
            modeling_error: DomainKernelError | None = None,
            modeling_errors: tuple[DomainKernelError, ...] = (),
        ) -> None:
            caller = asyncio.current_task()
            if caller is self.original and status is RunStatus.RECONCILING:
                self.checkpoints["original"] = (worker.lease.owner, worker.run.snapshot.version)
                self.original_waiting.set()
                _ = await asyncio.wait_for(self.release_original.wait(), timeout=self._timeout)
            elif caller is self.resumed and status is RunStatus.EXTRACTING:
                self.checkpoints["resumed"] = (worker.lease.owner, worker.run.snapshot.version)
                self.resume_waiting.set()
                _ = await asyncio.wait_for(self.release_resume.wait(), timeout=self._timeout)
            await checkpoint(
                workflow,
                worker=worker,
                status=status,
                task=task,
                report=report,
                consolidated=consolidated,
                modeling_error=modeling_error,
                modeling_errors=modeling_errors,
            )

        monkeypatch.setattr(DiscoveryWorkflow, "_checkpoint", pause_checkpoint)

    async def close(self) -> None:
        tasks = [caller for caller in (self.original, self.resumed) if caller is not None]
        for caller in tasks:
            if not caller.done():
                _ = caller.cancel()
        _ = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=self._timeout
        )


async def test_discovery_takeover_fences_original_checkpoint_at_same_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, revision = await _workspace(path=tmp_path, gateway=None)
    now = datetime.now(tz=UTC)
    timeout = 10
    gates = _DiscoveryTakeoverGates(timeout=timeout)

    async def open_model() -> Model:
        client = Client(
            config=ClientConfiguration(base_dir=tmp_path, model_gateway=_V23Gateway()),
            integrations=ClientIntegrations(
                transactions=SQLiteUnitOfWorkFactory(settings=settings, clock=lambda: now)
            ),
        )
        project = await client.get_project(name="recruitment")
        return await project.get_model(name="locators")

    settings = SQLiteSettings(path=tmp_path / ".domain-kernel/state.sqlite3")
    initial_model = await open_model()
    successor_model = await open_model()
    gates.install(monkeypatch=monkeypatch)
    original = asyncio.create_task(initial_model.discover(actor="editor", sources=(revision,)))
    gates.original = original
    try:
        _ = await asyncio.wait_for(gates.original_waiting.wait(), timeout=timeout)
        (interrupted,) = (await initial_model.list_discovery_runs()).items
        assert interrupted.status is RunStatus.EXTRACTING
        now += timedelta(minutes=2)
        resumed = asyncio.create_task(
            successor_model.resume_discovery(actor="operator", run_id=interrupted.id)
        )
        gates.resumed = resumed
        _ = await asyncio.wait_for(gates.resume_waiting.wait(), timeout=timeout)
        original_owner, original_version = gates.checkpoints["original"]
        resumed_owner, resumed_version = gates.checkpoints["resumed"]
        assert original_owner != resumed_owner
        persisted = await successor_model.get_discovery_run(run_id=interrupted.id)
        assert persisted == interrupted
        assert original_version == resumed_version == persisted.version

        gates.release_original.set()
        rejected = False
        try:
            _ = await asyncio.wait_for(original, timeout=timeout)
        except StaleStateError:
            rejected = True
        assert await successor_model.get_discovery_run(run_id=interrupted.id) == persisted
        assert rejected

        gates.release_resume.set()
        recovered = await asyncio.wait_for(resumed, timeout=timeout)
        assert recovered.id == interrupted.id
        assert recovered.status is RunStatus.NEEDS_REVIEW
        assert await successor_model.get_discovery_run(run_id=recovered.id) == recovered
        assert len((await successor_model.list_review_cases(run_id=recovered.id)).items) == 1
    finally:
        await gates.close()


async def test_models_review_the_same_source_independently(tmp_path: Path) -> None:
    gateway = _V23Gateway()
    first, revision = await _workspace(path=tmp_path, gateway=gateway)
    other_client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway))
    project = await other_client.get_project(name="recruitment")
    second = await project.create_model(
        actor="editor",
        name="reference-index",
        kind=ModelKind.OBSERVED,
        description="Describe the current index of source provisions.",
    )
    first_run = await first.discover(actor="editor", sources=(revision,))
    second_run = await second.discover(actor="editor", sources=(revision,))
    (first_case,) = (await first.list_review_cases(run_id=first_run.id)).items
    (second_case,) = (await second.list_review_cases(run_id=second_run.id)).items
    assert first_case.id != second_case.id
    assert first_case.definitions[0].id != second_case.definitions[0].id
    assert first_run.context != second_run.context
    drafts = [r for r in gateway.requests if r.provider_stage == "schema-compact-draft"]
    assert drafts[0].inputs == drafts[1].inputs

    _ = await first.decide_review(
        actor="reviewer", case=first_case, decision=Accept(reason="Keep the local lookup code.")
    )
    assert (await second.list_review_cases(run_id=second_run.id)).items == (second_case,)
    assert (await second.compile(actor="editor")).content.definitions == ()
    assert len((await first.compile(actor="editor")).content.definitions) == 1


async def test_raw_response_replay_preserves_the_failed_field_without_inference(
    tmp_path: Path,
) -> None:

    provider = _Gateway(result=_RESPONSE.replace("[1]", "[9]"))
    path = tmp_path / "private" / "responses.sqlite3"
    recorder = LocalReplayGateway(path=path, profile="test-model-1", gateway=provider)
    model, revision = await _workspace(path=tmp_path, gateway=recorder)
    with pytest.raises(InferenceError) as caught:
        _ = await model.extract_proposals(source_revisions=[revision], actor="reader")
    assert caught.value.issue is not None
    assert caught.value.issue.code == "invalid_citation"
    offline = LocalReplayGateway(path=path, profile="test-model-1")
    response = await offline.generate(request=provider.requests[0])
    assert response.output_json == provider.result
    assert path.stat().st_mode & 0o077 == 0
    assert len(provider.requests) == 1


class _CitedClaim(BaseModel):
    claim_id: str
    kind: str
    evidence: list[dict[str, str | int]]


class _ClaimContext(BaseModel):
    claims: list[_CitedClaim]


class _Edge(BaseModel):
    edge: _CitedClaim


class _EdgeContext(BaseModel):
    edges: list[_Edge]


class _AuditAssessment(BaseModel):
    claim_id: str
    stage: str
    meaning: str
    status: str


class _AuditBatch(BaseModel):
    assessments: list[_AuditAssessment]


class _AuditTrail(BaseModel):
    batches: list[_AuditBatch]


def _field_grades(request: ModelRequest, *, edges: bool = False) -> dict[str, object]:
    payload = request.context_json or "{}"
    claims = (
        [e.edge for e in _EdgeContext.model_validate_json(payload).edges]
        if edges
        else _ClaimContext.model_validate_json(payload).claims
    )
    decisions: list[dict[str, object]] = []
    for claim in reversed(claims):
        present = {"status": "supported", "evidence": claim.evidence[0]}
        absent = {"status": "not_applicable", "evidence": None}
        roles = present if claim.kind == "relationship" else absent
        decisions.append(
            {
                "claim_id": claim.claim_id,
                "meaning": present,
                "actor": roles,
                "object": roles,
                "recipient": absent,
                "conditions": absent,
                "exceptions": absent,
                "modality": present,
                "reason": "Direct support.",
            }
        )
        if edges:
            decisions[-1]["object"] = {"status": "contradicted", "evidence": claim.evidence[0]}
            decisions[-1]["reason"] = "The object should be the provision."
    return {"verdicts": decisions}


@pytest.mark.parametrize("verification", ["fields", "aggregate"])
async def test_staged_discovery_requires_quoted_evidence_and_replays(
    tmp_path: Path, verification: Literal["fields", "aggregate"]
) -> None:
    pytest.importorskip("langgraph.graph")

    class Stages:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            data: dict[str, object]

            if "Check for omissions" in request.instructions:
                self.calls.append("coverage")
                data = {"claims": []}
            elif request.response_schema_json in {
                json.dumps(Verdicts.model_json_schema()),
                json.dumps(aggregate_verification.Verdicts.model_json_schema()),
            }:
                self.calls.append("verify")
                data = (
                    _field_grades(request)
                    if verification == "fields"
                    else {"verdicts": [{"index": 0, "status": "supported", "reason": "Cited."}]}
                )
            else:
                self.calls.append("extract")
                claim = {
                    "kind": "concept",
                    "name": "lookup-code",
                    "title": "Lookup code",
                    "meaning": "A code locates a provision.",
                    "source": None,
                    "target": None,
                    "evidence": [{"citation": 1, "quote": "This code locates a provision"}],
                    "conditions": [],
                    "exceptions": [],
                }
                data = {
                    "claims": [
                        claim,
                        {
                            **claim,
                            "name": "unfounded",
                            "evidence": [{"citation": 1, "quote": "absent"}],
                        },
                    ]
                }
            return ModelResponse(output_json=json.dumps(data), model_id="local/test")

    stages = Stages()
    gateway = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=stages,
        directory=tmp_path / "private",
        profile="test-v1",
        verification=verification,
    )
    requests: list[ModelRequest] = []

    class Capture:
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            requests.append(request)
            return await gateway.generate(request=request)

    model, revision = await _workspace(path=tmp_path, gateway=Capture())
    first = await model.extract_proposals(source_revisions=[revision], actor="editor")
    assert [p.definition.name for p in first.proposals] == ["lookup-code"]
    second = await model.extract_proposals(source_revisions=[revision], actor="editor")
    assert [p.definition.name for p in second.proposals] == ["lookup-code"]

    class Audit(BaseModel):
        claims: list[_CitedClaim]

    saved_ids = [
        Audit.model_validate_json((gateway.directory / (draft.run_id.value + ".json")).read_bytes())
        .claims[0]
        .claim_id
        for draft in (first, second)
    ]
    assert saved_ids[0] == saved_ids[1]
    assert stages.calls == ["extract", "coverage", "verify"]
    # A completed stage checkpoint can restore the same run even if its raw journal is archived.
    _ = (gateway.directory / "stages.sqlite3").rename(tmp_path / "archived.sqlite3")
    offline = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=None,
        directory=gateway.directory,
        profile="test-v1",
        verification=verification,
    )
    restored = await offline.generate(request=requests[0])
    assert "lookup-code" in restored.output_json
    assert "unfounded" not in restored.output_json
    assert not (gateway.directory / "stages.sqlite3").exists()


async def test_journal_does_not_redispatch_an_uncertain_or_unretained_call(tmp_path: Path) -> None:
    broken = _Gateway(failures=1)
    path = tmp_path / "receipt.db"
    journal = LocalReplayGateway(path=path, profile="test", gateway=broken)
    model, revision = await _workspace(path=tmp_path, gateway=journal)
    with pytest.raises(InferenceError, match="unresolved"):
        _ = await model.extract_proposals(source_revisions=[revision], actor="reader")
    assert len(broken.requests) == 1
    request = broken.requests[0]
    redacted = LocalReplayGateway(
        path=path, profile="digest-only", gateway=broken, retain_responses=False
    )
    _ = await redacted.generate(request=request)
    with pytest.raises(InferenceError, match="fingerprint"):
        _ = await LocalReplayGateway(path=path, profile="digest-only").generate(request=request)
    assert _RESPONSE.encode() not in path.read_bytes()


async def test_endpoint_check_quarantines_a_true_sentence_with_the_wrong_target(
    tmp_path: Path,
) -> None:
    pytest.importorskip("langgraph.graph")

    class Gateway:
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            basic = {
                "kind": "concept",
                "source": None,
                "target": None,
                "evidence": [{"quote": "This code locates a provision", "citation": 1}],
                "exceptions": [],
                "conditions": [],
                "meaning": "An internal application code.",
            }
            data: dict[str, object]
            if "Check directed endpoints" in request.instructions:
                data = _field_grades(request, edges=True)
            elif '"aliases"' in request.response_schema_json:
                data = {"aliases": []}
            elif "Verify claims" in request.instructions:
                data = _field_grades(request)
            elif "Check for omissions" in request.instructions:
                data = {"claims": []}
            else:
                data = {
                    "claims": [
                        {**basic, "name": "code", "title": "Code"},
                        {**basic, "name": "provision", "title": "Provision"},
                        {
                            **basic,
                            "kind": "relationship",
                            "name": "locates",
                            "title": "Locates",
                            "meaning": "The code locates a provision.",
                            "source": "provision",
                            "target": "code",
                        },
                    ]
                }
            return ModelResponse(output_json=json.dumps(data), model_id="local/test")

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=Gateway(),
        directory=tmp_path / "graph",
        profile="example",
        verification="fields",
    )
    model, revision = await _workspace(path=tmp_path, gateway=graph)
    draft = await model.extract_proposals(source_revisions=[revision], actor="reader")
    assert {p.definition.name for p in draft.proposals} == {"code", "provision"}
    report = (graph.directory / f"{draft.run_id.value}.json").read_text()
    assert "The object should be the provision." in report


async def test_repaired_meaning_keeps_the_original_claim_identity(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    initial = "Every code locates every provision."
    repaired = "This code locates a provision."
    claim = {
        "kind": "concept",
        "name": "code",
        "title": "Code",
        "meaning": initial,
        "source": None,
        "target": None,
        "conditions": [],
        "exceptions": [],
        "evidence": [{"citation": 1, "quote": "This code locates a provision"}],
    }

    class Gateway:
        claimed_id: str = ""

        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            data: dict[str, object]
            if "Check for omissions" in request.instructions:
                data = {"claims": []}
            elif "Repair disputed claims" in request.instructions:
                data = {"claims": [{**claim, "claim_id": self.claimed_id, "meaning": repaired}]}
            elif "Verify claims" in request.instructions:
                data = _field_grades(request)
                if not self.claimed_id:
                    verdicts = Verdicts.model_validate(data)
                    (verdict,) = verdicts.verdicts
                    self.claimed_id = verdict.claim_id
                    verdict.meaning.status = "partly_supported"
                    data = verdicts.model_dump()
            else:
                data = {"claims": [claim]}
            return ModelResponse(output_json=json.dumps(data), model_id="test")

    provider = Gateway()
    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=provider,
        directory=tmp_path / "graph",
        profile="test",
        verification="fields",
    )
    model, revision = await _workspace(path=tmp_path, gateway=graph)
    draft = await model.extract_proposals(source_revisions=[revision], actor="editor")
    assert [p.definition.meaning for p in draft.proposals] == [repaired]
    audit = _AuditTrail.model_validate_json(
        (graph.directory / f"{draft.run_id.value}.json").read_bytes()
    )
    assert [
        (a.stage, a.meaning, a.status, a.claim_id) for b in audit.batches for a in b.assessments
    ] == [
        ("verify", initial, "partly_supported", provider.claimed_id),
        ("repair", repaired, "supported", provider.claimed_id),
    ]
