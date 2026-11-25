from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, override

import pytest
from pydantic import BaseModel

from domain_kernel import LangGraphDiscoveryGateway, ModelGateway, ModelRequest, ModelResponse
from domain_kernel._shared.application.inference import TruncatedResponse, TruncatedResponseError
from domain_kernel.discovery.application.claim_extraction import Anchor, BatchResult, Claim
from domain_kernel.discovery.application.passage_ranking import rank_passages
from domain_kernel.discovery.infrastructure.langgraph_gateway import (
    _Execution,  # pyright: ignore[reportPrivateUsage] -- inspect actual staged evidence packaging
)
from tests.support.discovery.make_request import make_request

if TYPE_CHECKING:
    from pathlib import Path


def test_precise_terms_recover_separate_original_spans() -> None:
    spans = (
        "A crate may be moved upon approval from the warehouse team.",
        "Inspection starts when a gauge registers a pressure drop.",
        "The gauge records the pressure. Inspection ends after the valve closes.",
        "The team may register for a meal upon arrival.",
    )
    assert set(rank_passages(query="Gauge pressure and inspection", passages=spans, limit=2)) == {
        1,
        2,
    }
    assert rank_passages(query="日程変更", passages=["地球", "日程変更"], limit=1) == (1,)


def test_disjoint_evidence_abstains_and_repeated_spans_cannot_crowd_out_alternatives() -> None:
    spans = ("A gauge registers pressure.", "A gauge registers pressure.", "A gauge is calibrated.")
    assert rank_passages(query="gauge pressure", passages=spans, limit=3) == (0, 2)
    assert rank_passages(query="unrelated", passages=spans, limit=3) == ()


def test_a_referenced_heading_must_belong_to_the_cited_revision(tmp_path: Path) -> None:
    first = make_request(name="current", text="Read Section 4.", scope="", arm="inspect")
    other = make_request(name="other", text="Section 4\nUnrelated rules.", scope="", arm="inspect")
    part = first.inputs[0]
    req = replace(
        first,
        inputs=[
            part,
            other.inputs[0],
            replace(part, text="Section 4\nOpen valve."),
            replace(part, text="Section 16\nValve calibration is done elsewhere."),
        ],
    )
    engine = _Execution(
        config=LangGraphDiscoveryGateway(
            evidence_bound=False, gateway=None, directory=tmp_path, profile="fixture"
        ),
        request=req,
    )
    claim = engine.identify(
        Claim(
            kind="concept",
            name="valve",
            title="Valve",
            meaning="Open valve.",
            source=None,
            target=None,
            evidence=[Anchor(citation=1, quote=part.text)],
            conditions=[],
            exceptions=[],
        )
    )
    batch = BatchResult(passages=[1, 4], candidates=[claim])
    assert engine.verification_passages(batch) == [1, 3]


class _Packet(BaseModel):
    claims: list[dict[str, object]]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["truncated", "unattributed", "persistent", "partial"])
async def test_unusable_verifier_groups_recover_with_bounded_replay(
    tmp_path: Path,
    failure: str,
) -> None:
    class Capped(ModelGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            assert request.context_json is not None
            grouped = len(_Packet.model_validate_json(request.context_json).claims) > 1
            if failure == "persistent" or (grouped and failure == "unattributed"):
                return ModelResponse(
                    output_json='{"verdicts":[]}', model_id="fixture", output_tokens=9
                )
            if grouped and failure == "truncated":
                raise TruncatedResponseError(
                    response=TruncatedResponse(
                        fragment="unusable",
                        model_id="fixture",
                        provider_request_id="cutoff",
                        provider_endpoint="https://fixture.example",
                        input_tokens=20,
                        output_tokens=9,
                    )
                )
            return ModelResponse(
                output_json='{"verdicts":[{"index":0,"status":"supported","reason":"Cited."}]}',
                model_id="fixture",
                input_tokens=10,
                output_tokens=2,
            )

    req = make_request(
        name="source", text="Open the inlet. Close the outlet.", scope="", arm="review"
    )
    gateway = LangGraphDiscoveryGateway(
        evidence_bound=False, gateway=Capped(), directory=tmp_path, profile="fixture"
    )
    for provider in (gateway, replace(gateway, gateway=None)):
        engine = _Execution(config=provider, request=req)
        claims = [
            engine.identify(
                Claim(
                    kind="concept",
                    name=name,
                    title=name,
                    meaning=quote,
                    source=None,
                    target=None,
                    evidence=[Anchor(citation=1, quote=quote)],
                    conditions=[],
                    exceptions=[],
                )
            )
            for name, quote in [("inlet", "Open the inlet."), ("outlet", "Close the outlet.")]
        ]
        batch = await engine.check(BatchResult(passages=[1], candidates=claims), 0)
        expected = {"persistent": [], "partial": claims[:1]}.get(failure, claims)
        assert batch.accepted == expected
        assert [a.claim_id for a in batch.assessments] == [c.claim_id for c in claims]
        outputs = {"partial": [2], "persistent": [9, 9, 9]}.get(failure, [9, 2, 2])
        assert [r.output_tokens for r in engine.receipts] == outputs
        assert any(f.stage == "verify" and "split" in f.detail.lower() for f in batch.findings) == (
            failure != "partial"
        )
