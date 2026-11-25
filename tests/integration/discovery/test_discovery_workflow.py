"""Verify discovery isolation, evidence and repair through the public workflow."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import BaseModel

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    LangGraphDiscoveryGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
)
from domain_kernel.discovery.application import aggregate_verification
from domain_kernel.discovery.application.claim_extraction import Verdicts
from tests.support.discovery.create_discovery_workspace import (
    create_discovery_workspace,
)
from tests.support.discovery.v23_gateway import V23Gateway

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_models_review_the_same_source_independently(tmp_path: Path) -> None:
    gateway = V23Gateway()
    first, revision = await create_discovery_workspace(path=tmp_path, gateway=gateway)
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

    model, revision = await create_discovery_workspace(path=tmp_path, gateway=Capture())
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
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=graph)
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
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=graph)
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
