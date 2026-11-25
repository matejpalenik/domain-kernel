"""Exercise the built-in Decisions route through public discovery and review."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    CaseStatus,
    Client,
    ClientConfiguration,
    DiscoveryStage,
    DiscoveryStageRoute,
    InferenceError,
    LangGraphDiscoveryGateway,
    LiteLLMGateway,
    ModelKind,
    Person,
    PersonId,
    RelationshipDefinition,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel.discovery.application.endpoint_decisions import Audit
from domain_kernel.discovery.infrastructure import litellm_gateway, openai_decisions
from domain_kernel.discovery.infrastructure.checkpoints import StageCheckpoints

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel.shared.hashing import JsonValue

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
_MAP = TypeAdapter(dict[str, object])
_ROWS = TypeAdapter(list[dict[str, object]])
_PAIRS = (
    ("Aster", "approves", "Docket"),
    ("Cedar", "opens", "Ledger"),
    ("Rowan", "sends", "Parcel"),
    ("Hazel", "signs", "Invoice"),
    ("Birch", "reviews", "Register"),
)
_SCOPE = "Verify the directed responsibilities stated by the owner."
_DEADLINE = 5
_ELIGIBLE_COUNT = 2
type _Setting = Literal[
    "default", "opt-out", "custom", "foreign", "mixed", "timeout", "partial", "failed-fallback"
]


def _fixture_claims() -> tuple[str, list[dict[str, object]]]:
    claims: list[dict[str, object]] = []
    sentences: list[str] = []
    for subject, action, target in _PAIRS:
        meaning = f"{subject} {action} {target}."
        text = meaning if subject != "Rowan" else "If dispatched, Rowan sends Parcel."
        sentences.append(text)
        for name in (subject, target):
            definition = name if subject != "Hazel" or name != target else "Archived invoice."
            claims.append(
                {
                    "kind": "concept",
                    "name": name.lower(),
                    "title": name,
                    "meaning": definition,
                    "source": None,
                    "target": None,
                    "conditions": [],
                    "exceptions": [],
                    "evidence": [{"citation": 1, "quote": name}],
                }
            )
        conditions = (
            []
            if subject != "Rowan"
            else [
                {"text": "If dispatched", "evidence": [{"citation": 1, "quote": "If dispatched"}]}
            ]
        )
        claims.append(
            {
                "kind": "relationship",
                "name": f"{subject.lower()}-{action}-{target.lower()}",
                "title": meaning,
                "meaning": meaning,
                "source": (target if subject == "Birch" else subject).lower(),
                "target": (subject if subject == "Birch" else target).lower(),
                "conditions": conditions,
                "exceptions": [],
                "evidence": [{"citation": 1, "quote": text}],
            }
        )
    return " ".join(sentences), claims


def _answer_packet(*, body: JsonValue, setting: _Setting) -> tuple[object, str]:
    packet = _MAP.validate_python(body)
    assert packet["model"] == "gpt-6-luna"
    questions = _ROWS.validate_python(packet["questions"])
    assert len(questions) == _ELIGIBLE_COUNT
    assert "Aster approves Docket." in str(questions[0]["instructions"])
    assert "Cedar opens Ledger." in str(questions[1]["instructions"])
    replies = [
        {
            "type": "choice",
            "name": row["name"],
            "choice": "SUPPORTED",
            "probabilities": [
                {"value": "SUPPORTED", "probability": support},
                {"value": "CONTRADICTED", "probability": 0.01},
                {"value": "INSUFFICIENT_EVIDENCE", "probability": round(0.99 - support, 2)},
            ],
        }
        for row, support in zip(questions, (0.9, 0.89), strict=True)
    ]
    return {
        "answers": replies[:1] if setting == "partial" else replies,
        "usage": {"input_tokens": 40, "output_tokens": 8},
    }, "fixture-request"


@pytest.mark.parametrize(
    "setting",
    ["default", "opt-out", "custom", "foreign", "mixed", "timeout", "partial", "failed-fallback"],
)
async def test_default_decisions_and_fallback_in_public_discovery(  # noqa: PLR0915 - Check the same public draft, recovery and replay boundary.
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    setting: _Setting,
) -> None:
    text, claims = _fixture_claims()
    endpoint_requests: list[list[str]] = []
    sent: list[dict[str, object]] = []

    async def completion(**kwargs: object) -> object:
        assert kwargs["model"] == "openai/gpt-6-luna"
        assert kwargs["reasoning_effort"] == "xhigh"
        messages = _ROWS.validate_python(kwargs["messages"])
        context = _MAP.validate_json(TypeAdapter(str).validate_python(messages[-1]["content"]))
        packet = _MAP.validate_python(context["interpretation_context"])
        if "claims" in packet or "edges" in packet:
            raw = _ROWS.validate_python(packet.get("claims", packet.get("edges")))
            if "edges" in packet:
                endpoint_requests.append(
                    [
                        TypeAdapter(str).validate_python(_MAP.validate_python(row["edge"])["name"])
                        for row in raw
                    ]
                )
                if setting == "failed-fallback":
                    raise TimeoutError
            output = {
                "verdicts": [
                    {"index": i, "status": "supported", "reason": "Directly stated."}
                    for i in range(len(raw))
                ]
            }
        else:
            output = {"claims": [] if "prior_claims" in packet else claims}
        return {
            "model": "gpt-6-luna",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}],
        }

    async def classify(
        *, body: JsonValue, api_key: str, timeout_seconds: float, client_request_id: str
    ) -> tuple[object, str | None]:
        assert api_key == "fixture-key"
        assert client_request_id
        assert 0 < timeout_seconds <= _DEADLINE
        sent.append(_MAP.validate_python(body))
        if setting == "timeout":
            await asyncio.Future[None]()
        return _answer_packet(body=body, setting=setting)

    monkeypatch.setattr(litellm_gateway, "_completion", lambda: completion)
    monkeypatch.setattr(openai_decisions, "post", classify)
    transport = LiteLLMGateway(
        api_key="fixture-key",
        reasoning_effort="xhigh",
        completion=completion if setting == "custom" else None,
        api_base="https://provider.example.invalid/v1"
        if setting == "foreign"
        else litellm_gateway.OPENAI_API_BASE,
    )
    gateway = LangGraphDiscoveryGateway(
        gateway=transport,
        directory=tmp_path / "audit",
        profile="openai-luna-xhigh-fixture",
        proposal_batching=True,
        stage_timeout_seconds=0.2 if setting == "timeout" else 300.0,
        decisions_enabled=False if setting == "opt-out" else None,
        stage_routes={
            DiscoveryStage.ENDPOINTS: DiscoveryStageRoute(
                gateway=replace(transport, completion=completion),
                profile="fixture-custom-endpoints",
            )
        }
        if setting == "mixed"
        else {},
    )
    config = ClientConfiguration(base_dir=tmp_path, model_gateway=gateway)
    project = await Client(config=config).create_project(actor="editor", name="routing")
    source = await project.ingest_source(
        actor="editor",
        name="statement",
        source=Statement(
            text=text,
            speaker=Person(id=PersonId(value="owner"), name="Owner", role="Owner"),
            context=_SCOPE,
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="editor", name="duties", kind=ModelKind.OBSERVED, description=_SCOPE
    )
    if setting == "failed-fallback":
        with pytest.raises(InferenceError):
            _ = await model.extract_proposals(actor="editor", source_revisions=[source.revision])
        assert not (await model.list_review_cases()).items
        directory = gateway.directory / "checkpoints"
        (pointer,) = [path for path in directory.iterdir() if path.is_file()]
        snapshot = StageCheckpoints(directory=directory, key=pointer.name).load()
        assert snapshot is not None
        assert snapshot.stage == "reconcile"
        assert gateway.directory.joinpath("endpoint-decisions.sqlite3").is_file()
        return
    draft = await model.extract_proposals(actor="editor", source_revisions=[source.revision])
    alignment = await model.propose_alignment(actor="editor", discovery_id=draft.id)
    expected = [f"{left.lower()}-{action}-{right.lower()}" for left, action, right in _PAIRS]
    assert len(sent) == (0 if setting in ("opt-out", "custom", "mixed", "foreign") else 1)
    assert endpoint_requests == [expected[1:] if setting in ("default", "partial") else expected]
    cases = [
        item
        async for item in model.iter_review_cases(
            reconciliation_id=alignment.id, status=CaseStatus.PENDING
        )
    ]
    relationships = [
        d for case in cases for d in case.definitions if isinstance(d.body, RelationshipDefinition)
    ]
    assert {d.name for d in relationships} == set(expected)
    for relationship in relationships:
        assert relationship.evidence
        assert (await project.get_evidence(evidence=relationship.evidence[0])).excerpt == text
    if setting == "default":
        (path,) = (gateway.directory / draft.run_id.value).glob("*.json")
        audit = Audit.model_validate(_MAP.validate_json(path.read_bytes())["endpoint_decisions"])
        assert [route.reason for route in audit.routes] == [
            "supported",
            "below_threshold",
            "qualified_or_specialized",
            "endpoint_proof_required",
            "endpoint_proof_required",
        ]
        (receipt,) = audit.calls
        assert receipt.provider_request_id == "fixture-request"
        assert (receipt.input_tokens, receipt.output_tokens) == (40, 8)
        assert audit.routes[0].endpoint_spans == ((0, 5), (15, 21))
        cfg = config.model_copy(
            update={"model_gateway": replace(gateway, gateway=None, decisions_enabled=True)}
        )
        replay_project = await Client(config=cfg).get_project(name="routing")
        replay_model = await replay_project.get_model(name="duties")
        replay = await replay_model.extract_proposals(
            actor="editor", source_revisions=[source.revision], idempotency_key="offline"
        )
        assert [p.definition.name for p in replay.proposals] == [
            p.definition.name for p in draft.proposals
        ]
        assert len(sent) == 1
        assert len(endpoint_requests) == 1
