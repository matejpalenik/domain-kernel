"""Verify the opt-in endpoint repair through the public extraction path."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, override

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    Client,
    ClientConfiguration,
    LangGraphDiscoveryGateway,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    RelationshipDefinition,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel._shared.application.inference import TruncatedResponse, TruncatedResponseError
from domain_kernel.configuration import InferencePolicy
from domain_kernel.discovery.infrastructure.sqlite_extraction import SQLiteExtraction
from domain_kernel.shared.errors import StaleStateError

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal

    from domain_kernel.discovery.domain.models import DiscoveryDraft
    from tests.support.persistence.database_backend import DatabaseBackend


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _claim(
    *, name: str, title: str, quote: str, source: str | None = None, target: str | None = None
) -> dict[str, object]:
    return {
        "kind": "concept" if source is None else "relationship",
        "name": name,
        "title": title,
        "meaning": quote,
        "source": source,
        "target": target,
        "evidence": [{"citation": 1, "quote": quote}],
        "conditions": [],
        "exceptions": [],
    }


class _LegacyCandidates(ModelGateway):
    """Supply the old mining shape and verify the proposed directed edges."""

    def __init__(self, *, claims: list[dict[str, object]]) -> None:
        self.claims: list[dict[str, object]] = claims

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        data: dict[str, object]
        if "claims" in context or "edges" in context:
            rows = TypeAdapter(list[object]).validate_python(
                context.get("claims", context.get("edges"))
            )
            data = {
                "verdicts": [
                    {"index": n, "status": "supported", "reason": "The source supports the roles."}
                    for n, _ in enumerate(rows)
                ]
            }
        elif "prior_claims" in context:
            data = {"claims": []}
        else:
            data = {"claims": self.claims}
        return ModelResponse(output_json=json.dumps(data), model_id="test/repair")


class _MissingEndpoint(_LegacyCandidates):
    def __init__(self, *, quote: str, truncate_multiple: bool) -> None:
        super().__init__(
            claims=[
                _claim(name="turin", title="Turin", quote=quote),
                _claim(
                    name="held-in",
                    title="Held in",
                    quote=quote,
                    source="winter-games",
                    target="turin",
                ),
            ],
        )
        self.quote: str = quote
        self.truncate_multiple: bool = truncate_multiple
        self.window_sizes: list[int] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        if context.get("missing_endpoint_names") == ["winter-games"]:
            excerpts = TypeAdapter(list[dict[str, object]]).validate_python(
                context["focus_excerpts"]
            )
            self.window_sizes.append(len(excerpts))
            if self.truncate_multiple and len(excerpts) > 1:
                raise TruncatedResponseError(
                    response=TruncatedResponse(
                        fragment="{",
                        model_id="test/recovery",
                        provider_request_id=None,
                        provider_endpoint="https://fixture.example",
                        input_tokens=10,
                        output_tokens=10,
                    )
                )
            return ModelResponse(
                output_json=json.dumps(
                    {
                        "claims": [
                            _claim(name="winter-games", title="Winter Games", quote=self.quote)
                        ]
                    }
                ),
                model_id="test/recovery",
            )
        return await super().generate(request=request)


class _HeldRepair(_LegacyCandidates):
    def __init__(self, *, quote: str, scenario: str) -> None:
        super().__init__(
            claims=[
                _claim(name="turin", title="Turin", quote="Turin"),
                _claim(
                    name="held-in",
                    title="Held in",
                    quote=quote,
                    source="1998" if scenario == "numeric" else "winter-games",
                    target="turin",
                ),
            ]
        )
        self.claims[1]["conditions"] = [
            {
                "text": "If travel was permitted.",
                "evidence": [{"citation": 1, "quote": "if travel was permitted"}],
            }
        ]
        self.scenario: str = scenario
        self.calls: int = 0

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        if "held_claims" not in context:
            return await super().generate(request=request)
        self.calls += 1
        if self.scenario == "truncated":
            raise TruncatedResponseError(
                response=TruncatedResponse(
                    fragment="{",
                    model_id="fixture",
                    provider_request_id=None,
                    provider_endpoint="https://fixture.example",
                    input_tokens=10,
                    output_tokens=8192,
                )
            )
        return ModelResponse(
            output_json=json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "source": {
                                "key": None,
                                "quote": {
                                    "swapped": "Turin",
                                    "numeric": "1998",
                                }.get(self.scenario, "Winter Games"),
                            },
                            "target": None,
                        }
                    ]
                }
            ),
            model_id="fixture",
        )


@pytest.mark.parametrize("scenario", ["recovered", "truncated", "swapped", "rollback", "numeric"])
async def test_held_endpoint_repair_is_additive_and_persists_unresolved_claims(
    tmp_path: Path,
    database_backend: DatabaseBackend,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    quote = "The Winter Games were held in Turin if travel was permitted."
    if scenario == "numeric":
        quote = "1998 marked the launch of the Turin project if travel was permitted."
    provider = _HeldRepair(quote=quote, scenario=scenario)
    gateway = LangGraphDiscoveryGateway(
        directory=tmp_path / "audit",
        profile="fixture/held",
        gateway=provider,
        proposal_batching=True,
        held_endpoint_repair=True,
    )
    config = database_backend.config.model_copy(
        update={
            "model_gateway": gateway,
            "inference": InferencePolicy(max_proposals=1),
        }
    )
    project = await Client(config=config).create_project(actor="reviewer", name="test")
    captured = await project.ingest_source(
        actor="reviewer",
        name="article",
        source=Statement(
            text=quote,
            speaker=Person(id=PersonId(value="editor"), name="Editor", role="Publisher"),
            context="Winter Games",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="reviewer", name="sports", kind=ModelKind.OBSERVED, description="Sports events."
    )
    if scenario == "rollback":
        complete = SQLiteExtraction.complete

        async def interrupted(
            repository: SQLiteExtraction, *, draft: DiscoveryDraft, batch_size: int | None = None
        ) -> None:
            await complete(repository, draft=draft, batch_size=batch_size)
            raise StaleStateError(message="Interrupt before the batched draft transaction commits.")

        with monkeypatch.context() as edits:
            edits.setattr(SQLiteExtraction, "complete", interrupted)
            with pytest.raises(StaleStateError, match="Interrupt before"):
                _ = await model.extract_proposals(
                    actor="reviewer",
                    source_revisions=[captured.revision],
                    idempotency_key="recover",
                )
        assert not (await model.list_review_cases()).items
        offline = config.model_copy(update={"model_gateway": replace(gateway, gateway=None)})
        resumed_project = await Client(config=offline).get_project(name="test")
        resumed_model = await resumed_project.get_model(name="sports")
        draft = await resumed_model.extract_proposals(
            actor="reviewer", source_revisions=[captured.revision], idempotency_key="recover"
        )
    else:
        draft = await model.extract_proposals(
            actor="reviewer", source_revisions=[captured.revision]
        )
    assert provider.calls == 1
    definitions = {p.definition.name: p.definition for p in draft.proposals}
    held = draft.held_relationships
    if scenario in ("truncated", "swapped"):
        assert set(definitions) == {"turin"}
        (claim,) = held
        assert (claim.source, claim.predicate, claim.target) == ("winter-games", "held-in", "turin")
        assert claim.reason
        assert tuple(claim.conditions) == ("If travel was permitted.",)
        assert (await project.get_evidence(evidence=claim.evidence[0].evidence)).excerpt == quote
    else:
        assert not held
        recovered_name = "concept-1998" if scenario == "numeric" else "winter-games"
        assert set(definitions) == {recovered_name, "held-in", "turin"}
        assert "If travel was permitted." in definitions["held-in"].meaning
        edge = definitions["held-in"].body
        assert isinstance(edge, RelationshipDefinition)
        assert edge.source_concept_id == definitions[recovered_name].id
        assert edge.target_concept_id == definitions["turin"].id


@pytest.mark.parametrize(
    "scenario",
    [
        "completed",
        "rolled-back-and-resumed",
        "truncated-window",
        "batching-only",
        "budget-exhausted",
    ],
)
async def test_targeted_recovery_persists_linked_proposals_across_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    scenario: Literal[
        "completed",
        "rolled-back-and-resumed",
        "truncated-window",
        "batching-only",
        "budget-exhausted",
    ],
) -> None:
    quote = "The Winter Games were held in Turin."
    truncate_multiple = scenario == "truncated-window"
    batching_only = scenario == "batching-only"
    provider = _MissingEndpoint(quote=quote, truncate_multiple=truncate_multiple)
    if batching_only:
        provider.claims.append(_claim(name="winter-games", title="Winter Games", quote=quote))
    graph = LangGraphDiscoveryGateway(
        directory=tmp_path / "audit",
        profile="fixture/recovery",
        gateway=provider,
        targeted_recovery=not batching_only,
        proposal_batching=batching_only,
    )
    config = ClientConfiguration(
        base_dir=tmp_path, model_gateway=graph, inference=InferencePolicy(max_proposals=1)
    )
    project = await Client(config=config).create_project(actor="reader", name="test")
    text = f"{quote} The city hosted several events."
    if scenario == "budget-exhausted":
        text += " " + " ".join(f"The event {i} attracted visitors." for i in range(20))
    capture = await project.ingest_source(
        actor="reader",
        name="input",
        source=Statement(
            text=text,
            speaker=Person(id=PersonId(value="editor"), name="Editor", role="Publisher"),
            context="Games",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="reader", name="games", kind=ModelKind.OBSERVED, description="Sporting events."
    )
    if scenario == "rolled-back-and-resumed":
        complete = SQLiteExtraction.complete

        async def interrupted(
            repository: SQLiteExtraction, *, draft: DiscoveryDraft, batch_size: int | None = None
        ) -> None:
            await complete(repository, draft=draft, batch_size=batch_size)
            raise StaleStateError(message="Simulate interruption after the proposal batch writes.")

        with monkeypatch.context() as edits:
            edits.setattr(SQLiteExtraction, "complete", interrupted)
            with pytest.raises(StaleStateError, match="Simulate interruption"):
                _ = await model.extract_proposals(
                    actor="reader", source_revisions=[capture.revision], idempotency_key="recover"
                )
        assert not (await model.list_review_cases()).items
        offline = replace(graph, gateway=None)
        reopened = await Client(
            config=config.model_copy(update={"model_gateway": offline})
        ).get_project(name="test")
        current = await reopened.get_model(name="games")
        resumed = await current.extract_proposals(
            actor="reader", source_revisions=[capture.revision], idempotency_key="recover"
        )
        assert {p.definition.name for p in resumed.proposals} == {
            "winter-games",
            "turin",
            "held-in",
        }
        return
    draft = await model.extract_proposals(
        actor="reader", source_revisions=[capture.revision], idempotency_key="recover"
    )
    expected_windows = {
        "completed": [2],
        "truncated-window": [2, 1, 1],
        "batching-only": [],
        "budget-exhausted": [7, 7],
    }
    assert provider.window_sizes == expected_windows[scenario]
    if scenario == "budget-exhausted":
        (report,) = (graph.directory / draft.run_id.value).glob("*.json")
        audit = TypeAdapter(dict[str, object]).validate_json(report.read_bytes())
        batches = TypeAdapter(list[dict[str, object]]).validate_python(audit["batches"])
        findings = TypeAdapter(list[dict[str, object]]).validate_python(batches[-1]["findings"])
        assert findings[0]["detail"] == "Deferred 1 focused excerpt(s) at the recovery budget."
    definitions = {p.definition.name: p.definition for p in draft.proposals}
    assert set(definitions) == {"winter-games", "turin", "held-in"}
    body = definitions["held-in"].body
    assert isinstance(body, RelationshipDefinition)
    assert body.source_concept_id == definitions["winter-games"].id
    assert body.target_concept_id == definitions["turin"].id
    reopened = await Client(config=config).get_project(name="test")
    current = await reopened.get_model(name="games")
    assert (
        await current.extract_proposals(
            actor="reader", source_revisions=[capture.revision], idempotency_key="recover"
        )
        == draft
    )


_SAME_SYSTEM = "The intake tool and archive tool are the same system."


@pytest.mark.parametrize(
    ("witness", "merged"),
    [
        (_SAME_SYSTEM, True),
        ("The intake tool and archive tool are the same type of system.", False),
        ("A vendor claimed the intake tool and archive tool are the same system.", False),
        ("Old notes stated that the intake tool and archive tool are the same system.", False),
        (
            f"{_SAME_SYSTEM} The intake tool and archive tool are separate systems.",
            False,
        ),
    ],
)
async def test_default_requires_source_identity_without_holding_ordinary_edges(
    tmp_path: Path, *, witness: str, merged: bool
) -> None:
    reads = "The intake tool reads the report."
    files = "The archive tool files the certificate."
    french = "La responsable valide le dossier."
    gateway = LangGraphDiscoveryGateway(
        directory=tmp_path / "audit",
        profile="fixture/legacy-identity",
        gateway=_LegacyCandidates(
            claims=[
                _claim(name="intake-tool", title="Intake tool", quote=reads),
                _claim(name="archive-tool", title="Archive tool", quote=files),
                _claim(name="report", title="Report", quote=reads),
                _claim(name="certificate", title="Certificate", quote=files),
                _claim(name="manager", title="Manager role", quote=french),
                _claim(name="file", title="File", quote=french),
                _claim(
                    name="reads", title="Reads", quote=reads, source="intake-tool", target="report"
                ),
                _claim(
                    name="files",
                    title="Files",
                    quote=files,
                    source="archive-tool",
                    target="certificate",
                ),
                _claim(
                    name="approves", title="Approves", quote=french, source="manager", target="file"
                ),
            ]
        ),
    )
    assert gateway.binding_contract is None
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway))
    project = await client.create_project(actor="reader", name="test")
    capture = await project.ingest_source(
        actor="reader",
        name="procedure",
        source=Statement(
            text=f"{reads} {files} {french} {witness}",
            speaker=Person(id=PersonId(value="editor"), name="Editor", role="Publisher"),
            context="Procedure",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="reader", name="operations", kind=ModelKind.OBSERVED, description="Operations."
    )
    draft = await model.extract_proposals(actor="reader", source_revisions=[capture.revision])
    edges = {
        proposal.definition.name: proposal.definition.body
        for proposal in draft.proposals
        if isinstance(proposal.definition.body, RelationshipDefinition)
    }
    assert set(edges) == {"reads", "files", "approves"}
    assert (edges["reads"].source_concept_id == edges["files"].source_concept_id) is merged
    assert not draft.relationship_bindings
    (report,) = (gateway.directory / draft.run_id.value).glob("*.json")
    identity = TypeAdapter(dict[str, object]).validate_json(report.read_bytes())
    aliases = TypeAdapter(list[dict[str, object]]).validate_python(identity["aliases"])
    if merged:
        (alias,) = aliases
        assert alias["identity_witness"] == {"citation": 1, "quote": witness}
    else:
        assert not aliases


@pytest.mark.parametrize("same", [True, False])
async def test_repair_requires_explicit_identity_and_retains_both_mentions(
    tmp_path: Path, *, same: bool
) -> None:
    ranks = "The screening tool (HR-017) ranks candidates."
    books = "The scheduling tool books interviews."
    witness = (
        "The screening tool and scheduling tool are the same application, HireFlow (HR-017)."
        if same
        else "The screening tool and scheduling tool are the same type of application."
    )
    clerk = "I am the HR clerk."
    writes = "I create a job description."
    reported = "A vacancy is reported to me."
    submits = "I am submitting the job description for consideration."
    graph = LangGraphDiscoveryGateway(
        directory=tmp_path / "audit",
        profile="test/repair",
        binding_version="v3",
        gateway=_LegacyCandidates(
            claims=[
                _claim(name="screening-tool", title="Screening tool", quote=ranks),
                _claim(name="scheduling-tool", title="Scheduling tool", quote=books),
                _claim(name="candidates", title="Candidates", quote=ranks),
                _claim(name="interviews", title="Interviews", quote=books),
                _claim(name="hr-clerk", title="HR clerk", quote=clerk),
                _claim(name="job-description", title="Job description", quote=writes),
                _claim(name="vacancy", title="Vacancy", quote=reported),
                _claim(
                    name="ranks",
                    title="Ranks",
                    quote=ranks,
                    source="screening-tool",
                    target="candidates",
                ),
                _claim(
                    name="books",
                    title="Books",
                    quote=books,
                    source="scheduling-tool",
                    target="interviews",
                ),
                _claim(
                    name="creates",
                    title="Creates",
                    quote=writes,
                    source="hr-clerk",
                    target="job-description",
                ),
                _claim(
                    name="is-reported-to",
                    title="Vacancy reported to HR clerk",
                    quote=reported,
                    source="vacancy",
                    target="hr-clerk",
                ),
            ]
        ),
    )
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=graph))
    project = await client.create_project(actor="reviewer", name="test")
    capture = await project.ingest_source(
        actor="reviewer",
        name="manual",
        source=Statement(
            text=f"{ranks} {books} {witness} {clerk} {reported} {writes} {submits}",
            speaker=Person(id=PersonId(value="editor"), name="Editor", role="Publisher"),
            context="Policy",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="reviewer", name="hiring", kind=ModelKind.OBSERVED, description="Hiring."
    )
    draft = await model.extract_proposals(actor="reviewer", source_revisions=[capture.revision])
    edges = {
        p.definition.name: p.definition
        for p in draft.proposals
        if isinstance(p.definition.body, RelationshipDefinition)
    }
    assert set(edges) == {"ranks", "books", "creates", "is-reported-to"}
    first, second = edges["ranks"].body, edges["books"].body
    assert isinstance(first, RelationshipDefinition)
    assert isinstance(second, RelationshipDefinition)
    assert (first.source_concept_id == second.source_concept_id) is same
    bound = {edge.relationship_id: edge for edge in draft.relationship_bindings}
    first_binding, second_binding = (bound[edges[name].id] for name in ("ranks", "books"))
    assert first_binding.source is not None
    assert second_binding.source is not None
    assert first_binding.source.mention_id != second_binding.source.mention_id
    assert (
        any(
            w.quote.rstrip(".") == witness.rstrip(".")
            for binding in (first_binding, second_binding)
            for w in binding.identity_evidence
        )
        is same
    )
    clerk_binding = bound[edges["creates"].id]
    recipient_binding = bound[edges["is-reported-to"].id]
    assert recipient_binding.target is not None
    assert recipient_binding.target.quote == "me"
    assert clerk_binding.source is not None
    assert clerk_binding.source.quote == "I"
    assert any("I am the HR clerk" in w.quote for w in clerk_binding.identity_evidence)


async def test_held_repair_disambiguates_same_name_without_merging(tmp_path: Path) -> None:
    physical = "The archive keeps paper copies."
    digital = "The archive preserves digital records."
    provider = _LegacyCandidates(
        claims=[
            _claim(name="archive", title="Archive", quote=physical),
            _claim(name="archive", title="Archive", quote=digital),
            _claim(name="digital-records", title="Digital records", quote="digital records"),
            _claim(
                name="preserves",
                title="Preserves",
                quote=digital,
                source="archive",
                target="digital-records",
            ),
        ]
    )
    graph = LangGraphDiscoveryGateway(
        directory=tmp_path / "audit",
        profile="fixture/ambiguous",
        gateway=provider,
        proposal_batching=True,
        held_endpoint_repair=True,
    )
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=graph)
    ).create_project(
        actor="reader",
        name="test",
    )
    source = await project.ingest_source(
        actor="reader",
        name="article",
        source=Statement(
            text=f"{physical} {digital}",
            speaker=Person(id=PersonId(value="author"), name="Author", role="Publisher"),
            context="Archive services.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="reader",
        name="archiving",
        kind=ModelKind.OBSERVED,
        description="Distinct archive services.",
    )
    draft = await model.extract_proposals(actor="reader", source_revisions=[source.revision])
    archives = {
        p.definition.meaning: p.definition.id
        for p in draft.proposals
        if p.definition.name.startswith("archive-scope-")
    }
    assert set(archives) == {physical, digital}
    edge = next(p.definition.body for p in draft.proposals if p.definition.name == "preserves")
    assert isinstance(edge, RelationshipDefinition)
    assert edge.source_concept_id == archives[digital]
    assert not draft.held_relationships
