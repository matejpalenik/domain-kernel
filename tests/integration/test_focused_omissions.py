"""Exercise the additive omission pass through the real staged gateway."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import TYPE_CHECKING, override

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    DiscoveryStage,
    DiscoveryStageRoute,
    LangGraphDiscoveryGateway,
    ModelGateway,
    ModelRequest,
    ModelResponse,
)
from domain_kernel._shared.application.inference import TruncatedResponse, TruncatedResponseError
from domain_kernel.discovery.application import focused_omissions
from domain_kernel.shared.hashing import JsonValue
from tests.support.discovery import make_request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_EXCERPT = "Edison invented the light bulb in 1879."


def _response(**payload: object) -> ModelResponse:
    return ModelResponse(output_json=json.dumps(payload), model_id="test")


def _row(
    *, name: str, title: str, quote: str, source: str | None = None, target: str | None = None
) -> dict[str, object]:
    return {
        "kind": "concept" if source is None else "relationship",
        "name": name,
        "title": title,
        "meaning": title,
        "evidence": [{"citation": 1, "quote": quote}],
        "source": source,
        "target": target,
        "conditions": [],
        "exceptions": [],
    }


class _Fixture(ModelGateway):
    def __init__(self, *, scenario: str) -> None:
        self.scenario: str = scenario
        self.focused: list[str] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        if isinstance(phase := context.get("focused_phase"), str):
            self.focused.append(phase)
            assert request.max_output_tokens == focused_omissions.MAX_TOKENS
            if self.scenario == "invalid":
                return ModelResponse(output_json="malformed", model_id="test")
            if self.scenario == "timeout":
                _ = await asyncio.Event().wait()
            if self.scenario == "truncate":
                raise TruncatedResponseError(
                    response=TruncatedResponse(
                        fragment=None,
                        model_id="test",
                        provider_request_id=None,
                        provider_endpoint="https://example.test",
                        input_tokens=100,
                        output_tokens=focused_omissions.MAX_TOKENS,
                    )
                )
            if phase == "extract":
                text = request.inputs[0].text
                assert text == _EXCERPT
                return _response(
                    claims=[
                        {
                            **_row(
                                name="invents",
                                title="Edison invented the light bulb",
                                quote=text,
                                source="bulb" if self.scenario == "reversed" else "edison",
                                target="edison" if self.scenario == "reversed" else "bulb",
                            ),
                            "conditions": [
                                {"text": "In 1879.", "evidence": [{"citation": 1, "quote": "1879"}]}
                            ],
                        }
                    ]
                )
            status = (
                "contradicted"
                if self.scenario == "reversed" and phase == "endpoints"
                else "supported"
            )
            return _response(verdicts=[{"index": 0, "status": status, "reason": "Checked."}])
        if "prior_claims" in context:
            return _response(claims=[])
        if (packet := context.get("claims", context.get("edges"))) is not None:
            claims = TypeAdapter(list[object]).validate_python(packet)
            return _response(
                verdicts=[
                    {"index": i, "status": "supported", "reason": "Checked."}
                    for i, _ in enumerate(claims)
                ]
            )
        return _response(
            claims=[
                _row(name="edison", title="Edison", quote="Edison"),
                _row(name="bulb", title="light bulb", quote="light bulb"),
                _row(
                    name="associated",
                    title="Edison is associated with the light bulb",
                    quote="Edison invented the light bulb",
                    source="edison",
                    target="bulb",
                ),
            ]
        )


@pytest.mark.parametrize(
    "scenario", ["valid", "invalid", "truncate", "timeout", "reversed", "byte-limit"]
)
async def test_focused_pass_preserves_baseline_and_checks_added_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, scenario: str
) -> None:
    provider = _Fixture(scenario=scenario)
    req = make_request(name="edison", text=_EXCERPT, scope="Inventions.", arm="study")
    baseline_gateway = LangGraphDiscoveryGateway(
        directory=tmp_path / "baseline",
        gateway=provider,
        profile="focused/fixture",
        proposal_batching=True,
    )
    baseline = await baseline_gateway.generate(request=req)
    if scenario == "byte-limit":
        req = replace(req, discovery_output_bytes=len(baseline.output_json.encode()))
    if scenario == "timeout":
        monkeypatch.setattr(focused_omissions, "TIMEOUT_SECONDS", 0.05)
    candidate = replace(
        baseline_gateway,
        directory=tmp_path / "candidate",
        focused_omission_recovery=True,
        stage_routes={
            DiscoveryStage.FOCUSED_OMISSIONS: DiscoveryStageRoute(
                gateway=provider,
                profile="focused/fixture",
            )
        },
    )
    result = await candidate.generate(request=req)
    adapter = TypeAdapter(dict[str, list[dict[str, JsonValue]]])
    previous = adapter.validate_json(baseline.output_json)
    current = adapter.validate_json(result.output_json)
    assert current["concepts"] == previous["concepts"]
    assert current["relationships"][:1] == previous["relationships"]
    if scenario == "valid":
        assert current["relationships"][1]["source"] == "edison"
        assert current["relationships"][1]["target"] == "bulb"
        assert "In 1879." in str(current["relationships"][1]["meaning"])
    else:
        assert current == previous
    calls = (
        ["extract"]
        if scenario in {"invalid", "truncate", "timeout"}
        else ["extract", "verify", "endpoints"]
    )
    assert provider.focused == calls
    assert (await candidate.generate(request=req)).output_json == result.output_json
    assert provider.focused == calls
