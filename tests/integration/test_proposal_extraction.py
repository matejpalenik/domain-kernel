"""Exercise extraction, guarded replay and failure recovery with a detached gateway."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypedDict, final
from unittest.mock import AsyncMock

import pytest

from domain_kernel import (
    Accept,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DefinitionStatus,
    DiscoveryProgress,
    IdempotencyConflictError,
    InferenceError,
    MissingCapabilityError,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    RunStatus,
    Statement,
    StatementForm,
    StatementIntent,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import DiscoveryRunId, IngestedSource, Model, SourceRevision
    from tests.integration.conftest import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_RESPONSE = (
    '{"concepts":[{"name":"application-code","display_name":"Application code",'
    '"meaning":"A lookup code for a reviewed provision.","citations":[1],"confidence":null}],'
    '"relationships":[]}'
)
_TEXT = "This code locates a provision in our recruitment application."


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


async def _workspace(
    *,
    path: Path,
    gateway: _Gateway | None,
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


async def test_discovery_reopens_and_resumes_the_captured_request(
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _Gateway(result='{"concepts":', failures=0)
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

    fresh_gateway = _Gateway()
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
    assert first.instructions == second.instructions == "Capture the sourced application code."
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
    assert fresh_gateway.requests == [second]


@final
class _InterruptedGateway:
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
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=_Gateway()),
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


@final
class _PartialGateway:
    def __init__(self) -> None:
        self.fix_second = False
        self.calls: list[str] = []

    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        text = request.inputs[0].text
        self.calls.append(text)
        if text != _TEXT and not self.fix_second:
            raise InferenceError(message="The second source needs a corrected provider response.")
        return ModelResponse(output_json=_RESPONSE, model_id="recorded/partial")


async def test_partial_discovery_retries_only_the_unfinished_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _PartialGateway()
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway),
    ).create_project(actor="editor", name="partial")
    captures: list[IngestedSource] = []
    passages = (_TEXT, "A second document confirms the application code.")
    for index, excerpt in enumerate(passages, start=1):
        captures.append(
            await project.ingest_source(
                actor="editor",
                name=f"source-{index}",
                source=Statement(
                    text=excerpt,
                    speaker=Person(
                        id=PersonId(value="owner"), name="Aria", role="Application owner"
                    ),
                    context="Review the provision reference.",
                    form=StatementForm.QUOTATION,
                    intent=StatementIntent.ASSERTION,
                ),
            )
        )
    model = await project.create_model(
        actor="editor",
        name="work",
        kind=ModelKind.PROPOSED,
        description="Review source meanings.",
    )
    revisions = tuple(item.revision for item in captures)
    partial = await model.discover(actor="editor", sources=revisions, idempotency_key="partial")
    assert partial.status is RunStatus.PARTIALLY_FAILED
    (failure,) = partial.failures
    assert failure.source == captures[1].revision
    original = await model.list_review_cases(run_id=partial.id)
    assert len(original.items) == 1

    gateway.fix_second = True
    complete = await model.resume_discovery(actor="editor", run_id=partial.id)
    assert complete.id == partial.id
    assert complete.status is RunStatus.NEEDS_REVIEW
    assert gateway.calls == [*passages, passages[1]]
    first_page = await model.list_review_cases(
        run_id=complete.id, status=CaseStatus.PENDING, limit=1
    )
    assert first_page.next_cursor is not None
    read_page = AsyncMock(wraps=model.list_review_cases)
    monkeypatch.setattr(model, "list_review_cases", read_page)
    remaining = model.iter_review_cases(
        run_id=complete.id,
        status=CaseStatus.PENDING,
        page_size=1,
        cursor=first_page.next_cursor,
    )
    read_page.assert_not_awaited()
    async for item in remaining:
        assert item != first_page.items[0]
        break
    read_page.assert_awaited_once_with(
        run_id=complete.id,
        reconciliation_id=None,
        kind=None,
        status=CaseStatus.PENDING,
        limit=1,
        cursor=first_page.next_cursor,
    )
    restored = [item async for item in model.iter_review_cases(run_id=complete.id, page_size=1)]
    assert original.items[0] in restored
    assert {item.evidence[0].source for item in restored} == set(revisions)
    assert (
        await model.discover(actor="editor", sources=revisions, idempotency_key="partial")
        == complete
    )
    assert gateway.calls == [*passages, passages[1]]
