"""Exercise repeated predicates through discovery, reconciliation and the pending SQLite queue."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import pytest
from pydantic import BaseModel

from domain_kernel import (
    CaseStatus,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    ExternalLocation,
    LangGraphDiscoveryGateway,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    ParsedPayload,
    ParsedSource,
    ParsedSourceOrigin,
    ParsedSourceProvider,
    ParsedSourceResolver,
    ParsedText,
    Person,
    PersonId,
    RelationshipDefinition,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel.discovery.application.claim_extraction import (
    Alias,
    Aliases,
    Anchor,
    BatchResult,
    Claim,
    Claims,
    Finding,
    IdentifiedClaim,
    Qualification,
)
from tests.support.discovery.make_request import make_request

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from domain_kernel import ProcessingLimits

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _CandidateList(BaseModel):
    claims: list[object] = []
    edges: list[object] = []


class _RecordedStages(ModelGateway):
    def __init__(self, *, claims: list[Claim]) -> None:
        self.claims: list[Claim] = claims

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        frame = _CandidateList.model_validate_json(request.context_json or "{}")
        if frame.claims or frame.edges:
            data = json.dumps(
                {
                    "verdicts": [
                        {"index": i, "status": "supported", "reason": "Direct wording."}
                        for i in range(len(frame.claims or frame.edges))
                    ]
                }
            )
        elif "Check for omissions" in request.instructions:
            data = '{"claims":[]}'
        elif "Compare the supplied concept definitions" in request.instructions:
            data = '{"aliases":[]}'
        else:
            data = Claims(claims=self.claims).model_dump_json()
        return ModelResponse(output_json=data, model_id="test/stages")


@pytest.mark.parametrize(
    ("source", "predicate", "target_a", "target_b"),
    [
        ("go", "informs-about-assignment", "mpo", "sp"),
        ("reef", "surrounds", "grande-terre", "ile-des-pins"),
    ],
)
async def test_repeated_predicate_survives_into_distinct_evidence_backed_review_cases(
    tmp_path: Path, source: str, predicate: str, target_a: str, target_b: str
) -> None:
    pytest.importorskip("langgraph.graph")
    quote = f"{source} {predicate} {target_a} and {target_b} when active."
    anchor = Anchor(citation=1, quote=quote)
    concepts = [
        Claim(
            kind="concept",
            name=name,
            title=name,
            meaning=name,
            evidence=[anchor],
            source=None,
            target=None,
            conditions=[],
            exceptions=[],
        )
        for name in (source, target_a, target_b)
    ]
    links = [
        Claim(
            kind="relationship",
            name=predicate,
            title=predicate,
            meaning=f"{source} {predicate} {t}",
            source=source,
            target=t,
            evidence=[anchor],
            conditions=[],
            exceptions=[],
        )
        for t in (target_a, target_b, "unknown")
    ]
    qualified = links[0].model_copy(deep=True)
    qualified.conditions = [Qualification(text="when active", evidence=[anchor])]
    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=_RecordedStages(claims=[*concepts, *links, qualified]),
        directory=tmp_path / "audit",
        profile="test",
    )
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=graph)
    ).create_project(actor="auditor", name="example")
    document = await project.ingest_source(
        name="source",
        actor="auditor",
        source=Statement(
            text=quote,
            speaker=Person(id=PersonId(value="a"), name="Ari", role="Editor"),
            context="Diagram",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        name="model", actor="auditor", kind=ModelKind.OBSERVED, description="Review directed links."
    )
    result = await model.extract_proposals(
        source_revisions=[document.revision], actor="auditor", idempotency_key="same"
    )
    alignment = await model.propose_alignment(actor="auditor", discovery_id=result.id)
    cases = (await model.list_review_cases(reconciliation_id=alignment.id)).items
    definitions = [c.definitions[0] for c in cases]
    names: dict[object, str] = {d.id: d.name for d in definitions}
    edges = [(d, d.body) for d in definitions if isinstance(d.body, RelationshipDefinition)]
    assert sorted(
        (names[e.source_concept_id], names[e.target_concept_id]) for _, e in edges
    ) == sorted([(source, target_a), (source, target_b), (source, target_a)])
    assert len({d.name for d in definitions}) == len(definitions)
    assert all(d.display_name == predicate for d, _ in edges)
    assert sum("when active" in d.meaning for d, _ in edges) == 1
    assert all(
        c.evidence[0].source == document.revision and c.status is CaseStatus.PENDING for c in cases
    )
    same = await model.extract_proposals(
        source_revisions=[document.revision], actor="auditor", idempotency_key="same"
    )
    assert same == result


async def test_endpoint_check_reads_the_sentence_governing_a_fragment(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    text = "The reef surrounds Grande Terre as well as the Ile des Pins. Coral grows nearby."
    evidence = Anchor(citation=1, quote="as well as the Ile des Pins")
    rows = [
        Claim(
            kind="concept",
            name=n,
            title=n,
            meaning=n,
            source=None,
            target=None,
            evidence=[evidence],
            conditions=[],
            exceptions=[],
        )
        for n in ("reef", "island")
    ]
    rows.append(
        Claim(
            kind="relationship",
            name="surrounds",
            title="Surrounds",
            meaning="The reef surrounds the island.",
            source="reef",
            target="island",
            evidence=[evidence],
            conditions=[],
            exceptions=[],
        )
    )
    observed: list[str] = []

    class Capture(_RecordedStages):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if _CandidateList.model_validate_json(request.context_json or "{}").edges:
                observed.extend(p.text for p in request.inputs)
            return await super().generate(request=request)

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False, gateway=Capture(claims=rows), directory=tmp_path, profile="test"
    )
    _ = await graph.generate(
        request=make_request(name="reef", text=text, scope="Reefs", arm="test")
    )
    assert observed == [text]


async def test_aggregate_repair_only_receives_the_disputed_occurrence(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    text = "A coordinator informs an editor and a reviewer."
    req = make_request(name="roles", text=text, scope="Task roles", arm="test")
    anchor = Anchor(citation=1, quote=text)
    rows = [
        Claim(
            kind="concept",
            name=n,
            title=n,
            meaning=n,
            source=None,
            target=None,
            evidence=[anchor],
            conditions=[],
            exceptions=[],
        )
        for n in ("coordinator", "editor", "reviewer")
    ]
    links = [
        Claim(
            kind="relationship",
            name="informs",
            title="Informs",
            meaning=f"Informs {target}.",
            source="coordinator",
            target=target,
            evidence=[anchor],
            conditions=[],
            exceptions=[],
        )
        for target in ("editor", "reviewer")
    ]
    rows.extend(links)
    disputed: list[str] = []

    class Dispute(_RecordedStages):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            frame = _CandidateList.model_validate_json(request.context_json or "{}")
            if "Repair disputed claims" in request.instructions:

                class Parent(BaseModel):
                    claim: IdentifiedClaim

                class Frame(BaseModel):
                    disputed_claims: list[Parent]

                disputed.extend(
                    p.claim.target or ""
                    for p in Frame.model_validate_json(request.context_json or "{}").disputed_claims
                )
                return ModelResponse(output_json='{"claims":[]}', model_id="test/stages")
            if frame.claims:
                data = {
                    "verdicts": [
                        {
                            "index": i,
                            "status": "insufficient" if i == len(rows) - 1 else "supported",
                            "reason": "Inspect this recipient.",
                        }
                        for i in range(len(frame.claims))
                    ]
                }
                return ModelResponse(output_json=json.dumps(data), model_id="test/stages")
            return await super().generate(request=request)

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False, gateway=Dispute(claims=rows), directory=tmp_path, profile="test"
    )
    _ = await graph.generate(request=req)
    assert disputed == ["reviewer"]


async def test_omission_pass_identifies_only_missing_endpoint_definitions(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    text = "The coordinator informs the editor."
    anchor = Anchor(citation=1, quote=text)
    concept = Claim(
        kind="concept",
        name="coordinator",
        title="Coordinator",
        meaning="The coordinator.",
        source=None,
        target=None,
        conditions=[],
        exceptions=[],
        evidence=[anchor],
    )
    link = Claim(
        kind="relationship",
        name="informs",
        title="Informs",
        meaning=text,
        source="coordinator",
        target="editor",
        evidence=[anchor],
        conditions=[],
        exceptions=[],
    )
    missing: list[str] = []

    class Coverage(_RecordedStages):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if "Check for omissions" in request.instructions:

                class Frame(BaseModel):
                    unresolved_endpoint_names: list[str] = []

                missing.extend(
                    Frame.model_validate_json(
                        request.context_json or "{}"
                    ).unresolved_endpoint_names
                )
            return await super().generate(request=request)

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=Coverage(claims=[concept, link]),
        directory=tmp_path,
        profile="test",
    )
    _ = await graph.generate(
        request=make_request(name="task", text=text, scope="Process roles", arm="test")
    )
    assert missing == ["editor"]


async def test_homonyms_are_separate_pending_proposals_and_do_not_redirect_aliases(
    tmp_path: Path,
) -> None:
    pytest.importorskip("langgraph.graph")
    quote = (
        "A computer terminal is a device. A rail terminal is a station. The train visits a station."
    )
    anchor = Anchor(citation=1, quote=quote)
    rows = [
        Claim(
            kind="concept",
            name=name,
            title=name,
            meaning=meaning,
            source=None,
            target=None,
            evidence=[anchor],
            conditions=[],
            exceptions=[],
        )
        for name, meaning in (
            ("terminal", "A device."),
            ("terminal", "A station."),
            ("rail-terminal", "A station."),
            ("train", "A train."),
        )
    ]
    rows.extend(
        Claim(
            kind="relationship",
            name="visits",
            title="Visits",
            meaning="The train visits a station.",
            source="train",
            target=target,
            evidence=[anchor],
            conditions=[],
            exceptions=[],
        )
        for target in ("terminal", "rail-terminal")
    )

    class Terms(_RecordedStages):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if "Compare the supplied concept definitions" in request.instructions:
                return ModelResponse(
                    output_json=json.dumps(
                        {
                            "aliases": [
                                {
                                    "alternate": "rail-terminal",
                                    "preferred": "terminal",
                                    "alternate_quote": quote,
                                    "preferred_quote": quote,
                                    "reason": "Both definitions describe a station.",
                                }
                            ]
                        }
                    ),
                    model_id="fixture",
                )
            return await super().generate(request=request)

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=Terms(claims=rows),
        directory=tmp_path / "audit",
        profile="test",
    )
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=graph)
    ).create_project(actor="editor", name="terminology")
    model = await project.create_model(
        name="transport",
        description="Transport and computing terms.",
        actor="editor",
        kind=ModelKind.OBSERVED,
    )
    doc = await project.ingest_source(
        name="passage",
        actor="editor",
        source=Statement(
            text=quote,
            speaker=Person(id=PersonId(value="a"), name="Ana", role="Editor"),
            context="Glossary",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    run = await model.extract_proposals(
        source_revisions=[doc.revision], actor="editor", idempotency_key="scope"
    )
    alignment = await model.propose_alignment(actor="editor", discovery_id=run.id)
    defs = [
        c.definitions[0]
        for c in (await model.list_review_cases(reconciliation_id=alignment.id)).items
    ]
    assert {d.meaning for d in defs if d.display_name == "terminal"} == {"A device.", "A station."}
    (rail,) = [d for d in defs if d.name == "rail-terminal"]
    (edge,) = [d.body for d in defs if isinstance(d.body, RelationshipDefinition)]
    assert edge.target_concept_id == rail.id

    class Audit(BaseModel):
        findings: list[Finding]
        proposal_names_by_claim_id: dict[str, str]
        batches: list[BatchResult]

    audit = Audit.model_validate_json(next(graph.directory.glob("*.json")).read_bytes())
    (held,) = [c for batch in audit.batches for c in batch.accepted if c.target == "terminal"]
    assert held.claim_id not in audit.proposal_names_by_claim_id
    assert any(
        f.claim_id == held.claim_id and "ambiguous" in f.detail.lower() for f in audit.findings
    )


async def test_pending_proposal_includes_cross_referenced_field_evidence(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    pointer = "For leave entitlements and the qualifying condition, see Section 4."
    rule = "Employees may request leave after probation."
    condition = "after probation"
    anchor = Anchor(citation=1, quote=pointer)
    claim = Claim(
        kind="concept",
        name="leave-entitlement",
        title="Leave entitlement",
        meaning="Employees may request leave.",
        source=None,
        target=None,
        conditions=[Qualification(text=condition, evidence=[anchor])],
        exceptions=[],
        evidence=[anchor],
    )

    class Cited(_RecordedStages):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if _CandidateList.model_validate_json(request.context_json or "{}").claims:

                class Frame(BaseModel):
                    claims: list[IdentifiedClaim]

                (candidate,) = Frame.model_validate_json(request.context_json or "{}").claims
                absent = {"status": "not_applicable", "evidence": None}
                direct = {"status": "supported", "evidence": {"citation": 2, "quote": rule}}
                vote = {
                    "claim_id": candidate.claim_id,
                    "meaning": direct,
                    "modality": direct,
                    "actor": absent,
                    "object": absent,
                    "recipient": absent,
                    "exceptions": absent,
                    "reason": "Section 4 states the rule.",
                    "conditions": {
                        "status": "supported",
                        "evidence": {"citation": 2, "quote": condition},
                    },
                }
                return ModelResponse(
                    output_json=json.dumps({"verdicts": [vote]}), model_id="fixture"
                )
            return await super().generate(request=request)

    parts = [
        ParsedText(text=t, locator=ExternalLocation(key=key))
        for t, key in [(pointer, "pointer"), ("Section 4\n" + rule, "governing-clause")]
    ]
    origin = ParsedSourceOrigin(
        document_id="leave",
        document_revision="1",
        provider="capture",
        captured_at=datetime(2026, 11, 18, tzinfo=UTC),
    )

    class Resolver(ParsedSourceResolver):
        @override
        @asynccontextmanager
        async def open(
            self, *, origin: ParsedSourceOrigin, limits: ProcessingLimits
        ) -> AsyncGenerator[ParsedPayload]:
            yield ParsedPayload(origin=origin, parts=parts)

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        directory=tmp_path / "a",
        profile="fixture",
        gateway=Cited(claims=[claim]),
        verification="fields",
    )
    host = Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=graph),
        integrations=ClientIntegrations(
            parsed_source_providers=[ParsedSourceProvider(name="capture", resolver=Resolver())]
        ),
    )
    project = await host.create_project(name="example", actor="editor")
    model = await project.create_model(
        name="glossary", actor="editor", description="Leave policy", kind=ModelKind.OBSERVED
    )
    source = await project.ingest_source(
        name="policy", actor="editor", source=ParsedSource(origin=origin, parts=parts)
    )
    run = await model.extract_proposals(
        source_revisions=[source.revision], actor="editor", idempotency_key="stable"
    )
    alignment = await model.propose_alignment(actor="editor", discovery_id=run.id)
    (case,) = (await model.list_review_cases(reconciliation_id=alignment.id)).items
    assert {e.locator for e in case.evidence} == {p.locator for p in parts}

    class Report(BaseModel):
        claims: list[IdentifiedClaim]
        batches: list[BatchResult]

    audit = Report.model_validate_json(next(graph.directory.glob("*.json")).read_bytes())
    (final,) = audit.claims
    assert final.claim_id == audit.batches[0].candidates[0].claim_id
    assert Anchor(citation=2, quote=condition) in final.conditions[0].evidence
    assert Anchor(citation=2, quote=rule) in final.evidence


_IDENTITY = "The appellant is also called the petitioner."
_SELF_ACTION = "The appellant represented the petitioner and recorded it as self-representation."


class _IndexedEdge(BaseModel):
    index: int
    edge: dict[str, str | int | list[object] | None]


class _SelfActionFrame(BaseModel):
    edges: list[_IndexedEdge]


class _AppellantStages(_RecordedStages):
    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        if '"identity_witness"' in request.response_schema_json:
            return ModelResponse(
                output_json=json.dumps({"identity_witness": {"citation": 1, "quote": _IDENTITY}}),
                model_id="test/stages",
            )
        if '"confirmations"' in request.response_schema_json:
            frame = _SelfActionFrame.model_validate_json(request.context_json or "{}")
            confirmations = [
                {
                    "index": item.index,
                    "action": {"citation": 1, "quote": _SELF_ACTION}
                    if item.edge["meaning"] == _SELF_ACTION
                    else None,
                }
                for item in frame.edges
            ]
            return ModelResponse(
                output_json=json.dumps({"confirmations": confirmations}), model_id="test/stages"
            )
        if '"aliases"' in request.response_schema_json:
            return ModelResponse(
                output_json=json.dumps(
                    {
                        "aliases": [
                            {
                                "alternate": "appellant",
                                "preferred": "petitioner",
                                "alternate_quote": _IDENTITY,
                                "preferred_quote": _IDENTITY,
                                "reason": "Both names identify the same person.",
                            }
                        ]
                    }
                ),
                model_id="test/stages",
            )
        return await super().generate(request=request)


async def test_newly_reflexive_edges_require_evidence_of_the_action(tmp_path: Path) -> None:
    pytest.importorskip("langgraph.graph")
    concepts = [
        Claim(
            kind="concept",
            name=name,
            title=name,
            meaning="The party to this hearing.",
            source=None,
            target=None,
            evidence=[Anchor(citation=1, quote=_IDENTITY)],
            conditions=[],
            exceptions=[],
        )
        for name in ("appellant", "petitioner")
    ]
    edges = [
        Claim(
            kind="relationship",
            name=name,
            title=name,
            meaning=quote,
            source="appellant",
            target="petitioner",
            evidence=[Anchor(citation=1, quote=quote)],
            conditions=[],
            exceptions=[],
        )
        for name, quote in (("naming", _IDENTITY), ("represents", _SELF_ACTION))
    ]
    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=_AppellantStages(claims=[*concepts, *edges]),
        directory=tmp_path / "evidence",
        profile="test",
    )
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=graph))
    project = await client.create_project(name="hearing", actor="editor")
    document = await project.ingest_source(
        name="record",
        actor="editor",
        source=Statement(
            text=f"{_IDENTITY} {_SELF_ACTION}",
            speaker=Person(id=PersonId(value="hearing-secretary"), name="Ari", role="Editor"),
            context="Hearing record",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        name="roles",
        actor="editor",
        kind=ModelKind.OBSERVED,
        description="Model the participants and actions at this hearing.",
    )
    run = await model.extract_proposals(
        source_revisions=[document.revision], actor="editor", idempotency_key="record"
    )
    alignment = await model.propose_alignment(actor="editor", discovery_id=run.id)
    reopened = await client.get_project(name="hearing")
    saved = await reopened.get_model(name="roles")
    cases = [c async for c in saved.iter_review_cases(reconciliation_id=alignment.id)]
    definitions = {d.name: (d, c) for c in cases for d in c.definitions}
    assert set(definitions) == {"petitioner", "represents"}
    person, _ = definitions["petitioner"]
    action, case = definitions["represents"]
    assert isinstance(action.body, RelationshipDefinition)
    assert action.body.source_concept_id == person.id
    assert action.body.target_concept_id == person.id
    assert case.status is CaseStatus.PENDING
    assert all(e.source == document.revision for e in case.evidence)
    assert _SELF_ACTION in action.meaning


@pytest.mark.parametrize("distinct", [False, True])
async def test_alias_binding_rechecks_shared_source_excerpt(
    tmp_path: Path, *, distinct: bool
) -> None:
    pytest.importorskip("langgraph.graph")
    first = "Route Center A.B."
    alternate = "Lighthouse"
    statement = (
        f"The reporter may send a copy to {first} or {alternate}."
        if distinct
        else f"{first} ({alternate}) is the central receiving office."
    )
    action = f"{alternate} receives the dispatch note."
    identity = Anchor(citation=1, quote=statement)
    receipt = Anchor(citation=1, quote=action)
    concepts = [
        Claim(
            kind="concept",
            name=name,
            title=title,
            meaning=title,
            source=None,
            target=None,
            evidence=[evidence],
            conditions=[],
            exceptions=[],
        )
        for name, title, evidence in (
            ("route-center-a-b", first, identity),
            ("lighthouse", alternate, identity),
            ("dispatch-note", "Dispatch note", receipt),
        )
    ]
    edge = Claim(
        kind="relationship",
        name="receives",
        title="Receives",
        meaning=action,
        source="lighthouse",
        target="dispatch-note",
        evidence=[receipt],
        conditions=[],
        exceptions=[],
    )

    class ProposedAlias(_RecordedStages):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if '"aliases"' in request.response_schema_json:
                vote = Alias(
                    alternate="lighthouse",
                    preferred="route-center-a-b",
                    alternate_quote=statement,
                    preferred_quote=statement,
                    reason="Proposed shared identity.",
                )
                return ModelResponse(
                    output_json=Aliases(aliases=[vote]).model_dump_json(), model_id="test/stages"
                )
            if '"identity_witness"' in request.response_schema_json:
                proof = None if distinct else {"citation": 1, "quote": statement}
                return ModelResponse(
                    output_json=json.dumps({"identity_witness": proof}), model_id="test/stages"
                )
            return await super().generate(request=request)

    graph = LangGraphDiscoveryGateway(
        evidence_bound=False,
        gateway=ProposedAlias(claims=[*concepts, edge]),
        directory=tmp_path,
        profile="test",
    )
    request = make_request(
        name="office", text=f"{statement}\n{action}", scope="Describe document intake.", arm="test"
    )
    response = await graph.generate(request=request)

    class Edge(BaseModel):
        source: str
        target: str

    class Output(BaseModel):
        relationships: list[Edge]

    (found,) = Output.model_validate_json(response.output_json).relationships
    assert found.source == ("lighthouse" if distinct else "route-center-a-b")
    assert found.target == "dispatch-note"
    replay = LangGraphDiscoveryGateway(
        evidence_bound=False, gateway=None, directory=tmp_path, profile="test"
    )
    assert (await replay.generate(request=request)).output_json == response.output_json
