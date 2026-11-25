"""Preserve cross-sentence evidence when a staged inference request is split."""

from dataclasses import replace
from pathlib import Path
from typing import override

import pytest
from pydantic import JsonValue, TypeAdapter

from domain_kernel import EvidenceId, ExternalLocation, LangGraphDiscoveryGateway, ModelGateway
from domain_kernel.discovery.application.claim_extraction import BatchResult
from domain_kernel.discovery.infrastructure.langgraph_gateway import (
    _Execution,  # pyright: ignore[reportPrivateUsage] -- verify the split extraction stage
)
from domain_kernel.shared.application.inference import (
    InferenceInput,
    ModelRequest,
    ModelResponse,
    TruncatedResponse,
    TruncatedResponseError,
)
from tests.support.discovery.make_request import make_request

_FIRST = "Hidhir Hasbiallah is a footballer."
_SECOND = "He played for Gombak United."
_SENTENCES = 2


class _SplitProvider(ModelGateway):
    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, JsonValue]).validate_json(request.context_json or "{}")
        if len(request.inputs) == _SENTENCES and "primary_passages" not in context:
            raise TruncatedResponseError(
                response=TruncatedResponse(
                    fragment=None,
                    model_id="fixture",
                    provider_request_id=None,
                    provider_endpoint="fixture",
                    input_tokens=None,
                    output_tokens=None,
                )
            )
        if context.get("primary_passages") == [2] and len(request.inputs) == _SENTENCES:
            return ModelResponse(
                model_id="fixture",
                output_json=TypeAdapter(dict[str, JsonValue])
                .dump_json(
                    {
                        "claims": [
                            {
                                "kind": "relationship",
                                "name": "played-for",
                                "title": "Played for",
                                "meaning": "Hidhir Hasbiallah played for Gombak United.",
                                "source": "hidhir-hasbiallah",
                                "target": "gombak-united",
                                "evidence": [
                                    {"citation": 1, "quote": _FIRST},
                                    {"citation": 2, "quote": _SECOND},
                                ],
                                "conditions": [],
                                "exceptions": [],
                            }
                        ],
                    }
                )
                .decode(),
            )
        return ModelResponse(model_id="fixture", output_json='{"claims":[]}')


@pytest.mark.integration
@pytest.mark.asyncio
async def test_truncated_extraction_keeps_adjacent_sentence_identity(tmp_path: Path) -> None:
    request = make_request(name="context", text=_FIRST, scope="Sports teams", arm="split")
    evidence = request.inputs[0].evidence[0]
    other = replace(evidence, id=EvidenceId(value="second"), locator=ExternalLocation(key="second"))
    request = replace(
        request, inputs=[request.inputs[0], InferenceInput(text=_SECOND, evidence=[other])]
    )
    engine = _Execution(
        config=LangGraphDiscoveryGateway(
            gateway=_SplitProvider(),
            directory=tmp_path,
            profile="fixture",
            preserve_split_context=True,
        ),
        request=request,
    )
    state = await engine.extract({"batches": [BatchResult(passages=[1, 2])]})
    (claim,) = state["batches"][0].candidates
    assert (claim.source, claim.target) == ("hidhir-hasbiallah", "gombak-united")
    assert [(anchor.citation, anchor.quote) for anchor in claim.evidence] == [
        (1, _FIRST),
        (2, _SECOND),
    ]
