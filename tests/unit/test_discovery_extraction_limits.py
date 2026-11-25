"""A capped extractor can recover at existing source boundaries without admitting partial output."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, override

import pytest

from domain_kernel import LangGraphDiscoveryGateway, ModelGateway, ModelRequest, ModelResponse
from domain_kernel._shared.application.inference import TruncatedResponse, TruncatedResponseError
from domain_kernel.discovery.application.claim_extraction import (
    EXTRACT,
    INITIAL_EXTRACTION,
    OMISSIONS,
    Anchor,
    BatchResult,
    Claim,
    Claims,
)
from domain_kernel.discovery.infrastructure.langgraph_gateway import (
    _Execution,  # pyright: ignore[reportPrivateUsage] -- isolate the production extraction node
)
from tests.support.discovery import make_request

if TYPE_CHECKING:
    from pathlib import Path


class _Limited(ModelGateway):
    def __init__(self, *, always: bool = False) -> None:
        self.always: bool = always
        self.instructions: list[str] = []
        self.timeouts: list[float] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.instructions.append(request.instructions)
        self.timeouts.append(request.timeout_seconds)
        if self.always or len(request.inputs) > 1:
            raise TruncatedResponseError(
                response=TruncatedResponse(
                    fragment='{"claims":[',
                    model_id="fixture",
                    provider_request_id="cutoff",
                    provider_endpoint="https://fixture.example",
                    input_tokens=20,
                    output_tokens=9,
                )
            )
        text = request.inputs[0].text
        claim = Claim(
            kind="concept",
            name=text.split()[0],
            title=text,
            meaning=text,
            source=None,
            target=None,
            evidence=[Anchor(citation=1, quote=text)],
            conditions=[],
            exceptions=[],
        )
        return ModelResponse(
            output_json=Claims(claims=[claim]).model_dump_json(),
            model_id="fixture",
            output_tokens=4,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("omissions", [False, True])
async def test_truncated_extraction_bisects_then_replays_the_same_passages(
    tmp_path: Path, *, omissions: bool
) -> None:
    seed = make_request(name="source", text="blue document", scope="Documents", arm="test")
    req = replace(seed, inputs=[*seed.inputs, replace(seed.inputs[0], text="red document")])
    cfg = LangGraphDiscoveryGateway(
        evidence_bound=False, gateway=_Limited(), directory=tmp_path, profile="small"
    )
    for current in (cfg, replace(cfg, gateway=None)):
        engine = _Execution(config=current, request=req)
        batch = BatchResult(passages=[1, 2])
        if omissions:
            prior = engine.identify(
                Claim(
                    kind="concept",
                    name="document",
                    title="Document",
                    meaning="document",
                    source=None,
                    target=None,
                    conditions=[],
                    exceptions=[],
                    evidence=[Anchor(citation=1, quote="document")],
                )
            )
            batch.candidates.append(prior)
        checked = await engine.mine(batch, 0, omissions=omissions)
        assert checked.passages == [1, 2]
        assert [(c.name, c.evidence[0].citation) for c in checked.candidates] == [
            *([("document", 1)] if omissions else []),
            ("blue", 1),
            ("red", 2),
        ]
        assert [r.output_tokens for r in engine.receipts] == [9, 4, 4]
        assert len(batch.candidates) == int(omissions)


@pytest.mark.asyncio
async def test_a_truncated_atomic_passage_stays_incomplete(tmp_path: Path) -> None:
    req = make_request(name="record", text="One passage.", scope="", arm="test")
    cfg = LangGraphDiscoveryGateway(
        evidence_bound=False, gateway=_Limited(always=True), directory=tmp_path, profile="small"
    )
    engine = _Execution(config=cfg, request=req)
    source = BatchResult(passages=[1])
    with pytest.raises(TruncatedResponseError):
        _ = await engine.mine(source, 0, omissions=False)
    assert source.candidates == []
    assert [r.output_tokens for r in engine.receipts] == [9]


@pytest.mark.asyncio
@pytest.mark.parametrize(("requested", "expected"), [(90.0, 90.0), (900.0, 300.0)])
async def test_staged_request_applies_shared_timeout_cap(
    tmp_path: Path, *, requested: float, expected: float
) -> None:
    original = make_request(name="record", text="Record.", scope="Records", arm="timeout")
    provider = _Limited()
    engine = _Execution(
        config=LangGraphDiscoveryGateway(
            evidence_bound=False, gateway=provider, directory=tmp_path, profile="timeout"
        ),
        request=replace(original, timeout_seconds=requested),
    )
    _ = await engine.mine(BatchResult(passages=[1]), 0, omissions=False)
    assert provider.timeouts == [expected]


@pytest.mark.asyncio
@pytest.mark.parametrize(("requested", "expected"), [(900.0, 600.0), (450.0, 450.0)])
async def test_coverage_can_use_a_longer_configured_timeout_within_the_request_budget(
    tmp_path: Path, *, requested: float, expected: float
) -> None:
    original = make_request(name="record", text="Record.", scope="Records", arm="timeout")
    provider = _Limited()
    engine = _Execution(
        config=LangGraphDiscoveryGateway(
            evidence_bound=False,
            gateway=provider,
            directory=tmp_path,
            profile="timeout",
            stage_timeout_seconds=600,
        ),
        request=replace(original, timeout_seconds=requested),
    )
    _ = await engine.mine(BatchResult(passages=[1]), 0, omissions=True)
    assert provider.timeouts == [expected]


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf"), True])
def test_staged_gateway_rejects_invalid_timeout(tmp_path: Path, *, timeout: float) -> None:
    with pytest.raises(ValueError, match="positive finite stage timeout"):
        _ = LangGraphDiscoveryGateway(
            evidence_bound=False,
            gateway=None,
            directory=tmp_path,
            profile="timeout",
            stage_timeout_seconds=timeout,
        )


@pytest.mark.asyncio
async def test_standalone_mining_requests_use_distinct_stage_instructions(tmp_path: Path) -> None:
    request = make_request(name="record", text="Record.", scope="Documents", arm="audit")
    provider = _Limited()
    engine = _Execution(
        config=LangGraphDiscoveryGateway(
            evidence_bound=False, gateway=provider, directory=tmp_path, profile="audit"
        ),
        request=request,
    )
    draft = await engine.mine(BatchResult(passages=[1]), 0, omissions=False)
    _ = await engine.mine(draft, 0, omissions=True)
    assert provider.instructions == [
        request.instructions + "\n" + INITIAL_EXTRACTION,
        request.instructions + "\n" + OMISSIONS + EXTRACT,
    ]
    assert INITIAL_EXTRACTION not in provider.instructions[1]
