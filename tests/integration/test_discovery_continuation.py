"""Preserve ordering and replay across parallel standalone endpoint checks."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from threading import Event
from typing import TYPE_CHECKING, override

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    Client,
    ClientConfiguration,
    LangGraphDiscoveryGateway,
    LocalReplayGateway,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    Statement,
    StatementForm,
    StatementIntent,
)

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PARALLEL_ENDPOINT_GROUPS = 3
_CANCELLED_PROVIDER_CALL = 2


def _claim(
    *, name: str, quote: str, source: str | None = None, target: str | None = None
) -> dict[str, object]:
    return {
        "kind": "relationship" if source else "concept",
        "name": name,
        "title": name.title(),
        "meaning": quote,
        "source": source,
        "target": target,
        "evidence": [{"citation": 1, "quote": quote}],
        "conditions": [],
        "exceptions": [],
    }


def _response(**data: object) -> ModelResponse:
    return ModelResponse(output_json=json.dumps(data), model_id="fixture")


class _EndpointGroups(ModelGateway):
    def __init__(self, *, parallel: bool) -> None:
        self.parallel: bool = parallel
        self.in_flight: int = 0
        self.peak: int = 0
        self.ready: asyncio.Event = asyncio.Event()

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        if "edges" in context:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            if self.in_flight == _PARALLEL_ENDPOINT_GROUPS:
                self.ready.set()
            if self.parallel:
                _ = await asyncio.wait_for(self.ready.wait(), timeout=5)
            self.in_flight -= 1
        if (rows := context.get("edges", context.get("claims"))) is not None:
            return _answer_verdicts(rows=TypeAdapter(list[object]).validate_python(rows))
        if "prior_claims" in context:
            return _response(claims=[])
        return _response(
            claims=[
                _claim(name="alpha", quote="Alpha"),
                _claim(name="beta", quote="Beta"),
                *(
                    _claim(
                        name=f"edge-{i}", quote="Alpha sends Beta.", source="alpha", target="beta"
                    )
                    for i in range(24)
                ),
            ]
        )


def _answer_verdicts(*, rows: list[object]) -> ModelResponse:
    return _response(
        verdicts=[
            {"index": i, "status": "supported", "reason": "Cited."} for i, _ in enumerate(rows)
        ]
    )


async def test_parallel_endpoint_verdicts_preserve_serial_order(tmp_path: Path) -> None:

    outputs: list[tuple[str, ...]] = []
    for concurrency in (1, 3):
        base = tmp_path / str(concurrency)
        provider = _EndpointGroups(parallel=concurrency > 1)
        graph = LangGraphDiscoveryGateway(
            gateway=provider,
            directory=base / "audit",
            profile="fixture/endpoint-groups",
            proposal_batching=True,
            endpoint_concurrency=concurrency,
        )
        project = await Client(
            config=ClientConfiguration(base_dir=base, model_gateway=graph)
        ).create_project(actor="editor", name="test")
        capture = await project.ingest_source(
            actor="editor",
            name="input",
            source=Statement(
                text="Alpha sends Beta.",
                speaker=Person(id=PersonId(value="editor"), name="Editor", role="Publisher"),
                context="Procedure",
                form=StatementForm.QUOTATION,
                intent=StatementIntent.ASSERTION,
            ),
        )
        model = await project.create_model(
            actor="editor", name="process", kind=ModelKind.OBSERVED, description="A procedure."
        )
        draft = await model.extract_proposals(actor="editor", source_revisions=[capture.revision])
        assert provider.peak == concurrency
        outputs.append(tuple(p.definition.name for p in draft.proposals))
    assert outputs[0] == outputs[1]


class _CancelledResponse(ModelGateway):
    def __init__(self) -> None:
        self.calls: int = 0

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        del request
        self.calls += 1
        if self.calls == _CANCELLED_PROVIDER_CALL:
            raise asyncio.CancelledError
        return _response(claims=[])


@pytest.fixture
def endpoint_request() -> ModelRequest:
    from tests.support.discovery import make_request  # noqa: PLC0415 - Provides pinned fixture evidence.

    return replace(
        make_request(name="doc", text="A sends B.", scope="Scope", arm="test"), retry_cancelled=True
    )


async def test_endpoint_replay_reuses_completed_receipts_and_retries_cancelled_group(
    tmp_path: Path,
    endpoint_request: ModelRequest,
) -> None:
    provider = _CancelledResponse()
    gateway = LocalReplayGateway(
        path=tmp_path / "journal.sqlite3", profile="fixture/cancellation", gateway=provider
    )
    first = endpoint_request
    pending = replace(first, instructions="Check the other endpoint group.")
    good = await gateway.generate(request=first)
    with pytest.raises(asyncio.CancelledError):
        _ = await gateway.generate(request=pending)
    assert await gateway.generate(request=first) == good
    assert await gateway.generate(request=pending) == good
    assert provider.calls == 3  # noqa: PLR2004 - One successful, one cancelled, and one reopened call.


async def test_cancellation_during_endpoint_journal_reservation_releases_it(
    tmp_path: Path, endpoint_request: ModelRequest
) -> None:
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = Event()

    class PausedJournal(LocalReplayGateway):
        @override
        def _reserve(self, *, key: str, retry_cancelled: bool) -> ModelResponse | None:
            _ = loop.call_soon_threadsafe(entered.set)
            assert release.wait(timeout=5)
            return super()._reserve(key=key, retry_cancelled=retry_cancelled)

    provider = _CancelledResponse()
    journal = PausedJournal(
        path=tmp_path / "journal.sqlite3", profile="fixture/cancellation", gateway=provider
    )
    pending = asyncio.create_task(journal.generate(request=endpoint_request))
    try:
        _ = await asyncio.wait_for(entered.wait(), timeout=5)
        _ = pending.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        _ = await pending
    assert provider.calls == 0
    assert await journal.generate(request=endpoint_request) == _response(claims=[])
    assert provider.calls == 1
