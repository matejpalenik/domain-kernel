"""Verify the gate's fail-closed responses and pinning rules locally."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, final

import httpx
import pytest

from domain_kernel.discovery.application import endpoint_decisions
from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    Assessment,
    BatchResult,
    IdentifiedClaim,
)
from domain_kernel.discovery.application.claim_graph import ClaimGraph
from domain_kernel.discovery.infrastructure import openai_decisions
from tests.support.discovery.make_request import make_request

if TYPE_CHECKING:
    from domain_kernel.shared.json_value import JsonValue


def _choice(name: str, /) -> dict[str, JsonValue]:
    return {
        "type": "choice",
        "name": name,
        "choice": "SUPPORTED",
        "probabilities": [
            {"value": "SUPPORTED", "probability": 0.9},
            {"value": "CONTRADICTED", "probability": 0.05},
            {"value": "INSUFFICIENT_EVIDENCE", "probability": 0.05},
        ],
    }


def test_classification_failures_are_attributed_to_the_exact_question() -> None:
    malformed_mass = _choice("bad-mass")
    malformed_mass["probabilities"] = [{"value": "SUPPORTED", "probability": 0.99}]
    answer = endpoint_decisions.Reply(
        status="ok",
        seconds=0,
        answers=[
            _choice("valid"),
            _choice("duplicate"),
            _choice("duplicate"),
            {"type": "refusal", "name": "refused"},
            malformed_mass,
            _choice("wrong-choice") | {"choice": "CONTRADICTED"},
            _choice("bad-choice") | {"choice": True},
        ],
    )
    assert endpoint_decisions.outcomes(
        reply=answer,
        ids=("valid", "duplicate", "refused", "bad-mass", "wrong-choice", "bad-choice", "missing"),
    ) == {
        "valid": ("supported", 0.9),
        "duplicate": ("ambiguous_answer", None),
        "refused": ("refused", None),
        "bad-mass": ("malformed_answer", None),
        "wrong-choice": ("non_supporting_choice", 0.9),
        "bad-choice": ("malformed_answer", None),
        "missing": ("missing_answer", None),
    }


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("simple", "eligible"),
        ("alias", "alias_or_external_endpoint"),
        ("repaired", "changed_or_repaired"),
        ("reconciled", "changed_or_repaired"),
        ("cross-passage", "endpoint_proof_required"),
        ("scope", "scope_finding"),
    ],
)
def test_only_direct_unmodified_source_occurrences_can_bypass(
    *, variant: str, expected: str
) -> None:
    text = "Aster approves Docket."
    source = _row(name="aster", text="Aster")
    target = _row(name="docket", text="Docket")
    claim = _row(name="approves", text=text, source="aster", target="docket")
    request = make_request(name="duties", text=text, scope="Duties", arm="fixture")
    inputs = request.inputs
    assessments: list[Assessment] = []
    if variant == "cross-passage":
        inputs = (*inputs, replace(inputs[0], text="Aster discusses Docket."))
        target.evidence[0].citation = 2
    elif variant == "repaired":
        assessments.append(
            Assessment(
                stage="repair",
                claim_id=claim.claim_id,
                meaning=text,
                verdict=None,
                status="supported",
                detail="Repaired.",
            )
        )
    elif variant == "scope":
        prefix = "After review, Aster approves Docket."
        inputs = (replace(inputs[0], text=prefix),)
    projected = (
        claim.model_copy(update={"source": "docket", "target": "aster"})
        if variant == "reconciled"
        else claim
    )
    rows = [source, target, projected]
    graph = ClaimGraph(claims=rows, origins={row.claim_id: [row.claim_id] for row in rows})
    audit, candidates = endpoint_decisions.plan(
        graph=graph,
        batches=[
            BatchResult(passages=[1], accepted=[source, target, claim], assessments=assessments)
        ],
        inputs=inputs,
        blocked_names={"aster"} if variant == "alias" else set(),
    )
    (result,) = audit.routes
    assert result.reason == expected
    assert bool(candidates) is (variant == "simple")


def _row(
    *, name: str, text: str, source: str | None = None, target: str | None = None
) -> IdentifiedClaim:
    return IdentifiedClaim(
        kind="concept" if source is None else "relationship",
        claim_id=name,
        name=name,
        title=text,
        meaning=text,
        source=source,
        target=target,
        conditions=[],
        exceptions=[],
        evidence=[Anchor(citation=1, quote=text)],
    )


@pytest.mark.asyncio
async def test_openai_transport_submits_the_choice_json_to_the_official_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet: dict[str, JsonValue] = {"model": "gpt-6-luna", "questions": [{"name": "fixture"}]}
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, json={"answers": []}, headers={"x-request-id": "saved-provider-id"}
        )

    kwargs: list[dict[str, object]] = []

    def client(**options: object) -> httpx.AsyncClient:
        kwargs.append(options)
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    @final
    class Module:
        AsyncClient = staticmethod(client)
        TimeoutException = httpx.TimeoutException

    def load_module(_name: str) -> type[Module]:
        return Module

    monkeypatch.setattr(openai_decisions, "import_module", load_module)
    body, identifier = await openai_decisions.post(
        body=packet, api_key="fixture-key", timeout_seconds=0.5, client_request_id="fixture-id"
    )
    (request,) = calls
    assert str(request.url) == "https://api.openai.com/v1/decisions"
    assert request.headers["Authorization"] == "Bearer fixture-key"
    assert request.headers["X-Client-Request-Id"] == "fixture-id"
    assert kwargs == [{"timeout": 0.5, "follow_redirects": False, "trust_env": False}]
    assert body == {"answers": []}
    assert identifier == "saved-provider-id"
