"""Reopen occurrence-bound relationships through the public discovery API."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, override

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    ClientIntegrations,
    DefinitionId,
    DomainModelBuilder,
    ExternalLocation,
    InferenceError,
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
    StaleStateError,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel.discovery.application.claim_extraction import BatchResult, BoundClaim
from domain_kernel.discovery.application.endpoint_contract import BindingEnvelope
from tests.support.discovery.make_request import make_request

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from domain_kernel import ProcessingLimits

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_HOMONYM_COUNT = 2
_TEXT = (
    "Recruitment systems are intended to evaluate candidates. "
    "Selection systems rank applications. Selection systems are also recruitment systems."
)


def _anchor(quote: str, *, citation: int = 1) -> dict[str, object]:
    return {"citation": citation, "quote": quote}


def _mention(ref: str, quote: str, context: str | None = None) -> dict[str, object]:
    return {
        "ref": ref,
        "anchor": _anchor(quote),
        "context": context,
        "role": None,
        "approved_name": None,
    }


def _claim(
    *,
    name: str,
    title: str,
    meaning: str,
    quote: str,
    binding: str | tuple[str, str],
) -> dict[str, object]:
    mention = binding if isinstance(binding, str) else None
    source, target = (None, None) if isinstance(binding, str) else binding
    return {
        "kind": "concept" if mention else "relationship",
        "name": name,
        "title": title,
        "meaning": meaning,
        "evidence": [_anchor(quote)],
        "mention": mention,
        "source": source,
        "target": target,
        "modality": None,
        "qualifiers": [],
    }


class _RecordedGateway(ModelGateway):
    def __init__(self, *, extraction: dict[str, object]) -> None:
        self.extraction: dict[str, object] = extraction

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        result: dict[str, object]
        if "claims" in context or "edges" in context:
            records = TypeAdapter(list[dict[str, object]]).validate_python(
                context.get("claims", context.get("edges"))
            )
            result = {
                "verdicts": [
                    {
                        "index": i,
                        "status": "contradicted"
                        if record.get("name") == "reverse-evaluation"
                        else "supported",
                        "reason": "Check the actor against the cited text.",
                    }
                    for i, record in enumerate(records)
                ]
            }
        elif "disputed_claims" in context or "prior_claims" in context:
            result = {"mentions": [], "claims": []}
        elif "designations" in context:
            result = {"identity_witness": None}
        elif "concepts" in context:
            rows = TypeAdapter(list[dict[str, str | None]]).validate_python(context["concepts"])
            homonyms = [row for row in rows if row.get("title") == "Recruitment system"]
            aliases: list[dict[str, str | None]] = []
            if len(homonyms) == _HOMONYM_COUNT:
                first, second = homonyms
                aliases.append(
                    {
                        "alternate": first["name"],
                        "preferred": second["name"],
                        "alternate_quote": first["quote"],
                        "preferred_quote": second["quote"],
                        "reason": "Same label, with no explicit equivalence in the source.",
                    }
                )
            result = {"aliases": aliases}
        else:
            result = self.extraction
        return ModelResponse(output_json=json.dumps(result), model_id="test/evidence-bound")


def _recruitment() -> dict[str, object]:
    first = "Recruitment systems are intended to evaluate candidates."
    last = "Selection systems are also recruitment systems."
    return {
        "mentions": [
            _mention("r", "Recruitment systems", first),
            _mention("other", "recruitment systems", last),
            _mention("c", "candidates"),
        ],
        "claims": [
            _claim(
                name="recruitment-system",
                title="Recruitment system",
                meaning="A system intended to evaluate candidates.",
                quote=first,
                binding="r",
            ),
            _claim(
                name="recruitment-system",
                title="Recruitment system",
                meaning="A selection system identified as a recruitment system.",
                quote=last,
                binding="other",
            ),
            _claim(
                name="candidate",
                title="Candidate",
                meaning="A candidate evaluated in recruitment.",
                quote=first,
                binding="c",
            ),
            _claim(
                name="evaluates",
                title="Evaluates",
                meaning="Recruitment systems are intended to evaluate candidates.",
                quote=first,
                binding=("r", "c"),
            ),
            _claim(
                name="reverse-evaluation",
                title="Reversed evaluation",
                meaning="Candidates evaluate recruitment systems.",
                quote=first,
                binding=("c", "r"),
            ),
        ],
    }


async def test_relationship_reopens_with_the_intended_homonym(tmp_path: Path) -> None:
    gateway = LangGraphDiscoveryGateway(
        gateway=_RecordedGateway(extraction=_recruitment()),
        directory=tmp_path / "audit",
        profile="test",
        evidence_bound=True,
        binding_version="v1",
    )
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway))
    project = await client.create_project(actor="reviewer", name="test")
    source = await project.ingest_source(
        name="act",
        actor="reviewer",
        source=Statement(
            text=_TEXT,
            speaker=Person(id=PersonId(value="publisher"), name="Publisher", role="Publisher"),
            context="Source",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        name="recruitment",
        actor="reviewer",
        kind=ModelKind.OBSERVED,
        description="Recruitment and selection",
    )
    draft = await model.extract_proposals(source_revisions=[source.revision], actor="reviewer")
    alignment = await model.propose_alignment(actor="reviewer", discovery_id=draft.id)
    cases = (await model.list_review_cases(reconciliation_id=alignment.id)).items
    definitions = {d.id: d for c in cases for d in c.definitions}
    homonyms = [d for d in definitions.values() if d.display_name == "Recruitment system"]
    assert len(homonyms) == _HOMONYM_COUNT
    (edge,) = (d for d in definitions.values() if isinstance(d.body, RelationshipDefinition))
    assert isinstance(edge.body, RelationshipDefinition)
    assert isinstance(edge.body.source_concept_id, DefinitionId)
    assert isinstance(edge.body.target_concept_id, DefinitionId)
    assert (
        definitions[edge.body.source_concept_id].meaning
        == "A system intended to evaluate candidates."
    )
    assert definitions[edge.body.target_concept_id].display_name == "Candidate"
    evidence = next(c.evidence[0] for c in cases if edge in c.definitions)
    assert "evaluate candidates" in (await project.get_evidence(evidence=evidence)).excerpt
    (report,) = (gateway.directory / draft.run_id.value).glob("*.json")
    assert "No explicit source witness" in report.read_text()


class _BindingGateway(_RecordedGateway):
    """Return keyed endpoint verdicts and optionally retry an earlier identity."""

    def __init__(self, *, stale: bool = False, extraction: dict[str, object] | None = None) -> None:
        super().__init__(extraction=_recruitment() if extraction is None else extraction)
        self.stale: bool = stale

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        if "edges" not in context or '"binding_key"' not in request.response_schema_json:
            return await super().generate(request=request)
        rows = TypeAdapter(list[dict[str, object]]).validate_python(context["edges"])
        verdicts: list[dict[str, object]] = []
        for packet in reversed(rows):
            edge = TypeAdapter(dict[str, object]).validate_python(packet["edge"])
            verdicts.append(
                {
                    "claim_id": edge["claim_id"],
                    "binding_key": "earlier-binding" if self.stale else packet["binding_key"],
                    "status": "contradicted"
                    if edge["name"] == "reverse-evaluation"
                    else "supported",
                    "evidence": TypeAdapter(list[dict[str, object]]).validate_python(
                        edge["evidence"]
                    )[:1],
                    "reason": "The sentence gives the actor and the object.",
                }
            )
        return ModelResponse(
            output_json=json.dumps({"verdicts": verdicts}), model_id="test/stable-binding"
        )


@pytest.mark.parametrize("stale", [False, True])
async def test_stable_binding_reopens_directed_roles_and_holds_stale_verdicts(
    tmp_path: Path, *, stale: bool
) -> None:
    gateway = LangGraphDiscoveryGateway(
        gateway=_BindingGateway(stale=stale),
        directory=tmp_path / "audit",
        profile="test/stable",
        binding_version="v2",
    )
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway))
    project = await client.create_project(actor="reader", name="test")
    source = await project.ingest_source(
        actor="reader",
        name="policy",
        source=Statement(
            text=_TEXT,
            speaker=Person(id=PersonId(value="publisher"), name="Publisher", role="Publisher"),
            context="Policy",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="reader", name="recruitment", kind=ModelKind.OBSERVED, description="Recruitment"
    )
    draft = await model.extract_proposals(
        source_revisions=[source.revision], actor="reader", idempotency_key="once"
    )
    alignment = await model.propose_alignment(actor="reader", discovery_id=draft.id)
    reopened = await Client(config=ClientConfiguration(base_dir=tmp_path)).get_project(name="test")
    current = await reopened.get_model(name="recruitment")
    bindings = draft.relationship_bindings
    if stale:
        assert bindings
        assert all(item.relationship_id is None for item in bindings)
        return
    (linked,) = (item for item in bindings if item.relationship_id is not None)
    assert linked.source is not None
    assert linked.target is not None
    assert linked.relationship_id is not None
    cases = (await current.list_review_cases(reconciliation_id=alignment.id)).items
    definitions = {item.id: item for case in cases for item in case.definitions}
    edge = definitions[linked.relationship_id].body
    assert isinstance(edge, RelationshipDefinition)
    assert edge.source_concept_id == linked.source.definition_id
    assert edge.target_concept_id == linked.target.definition_id
    assert linked.source.definition_id is not None
    assert definitions[linked.source.definition_id].meaning == (
        "A system intended to evaluate candidates."
    )
    excerpt = (await reopened.get_evidence(evidence=linked.source.evidence)).excerpt
    assert excerpt[linked.source.start : linked.source.end] == "Recruitment systems"
    assert any(item.relationship_id is None for item in bindings)


@pytest.mark.parametrize("version", ["v1", "v2"])
async def test_bound_checkpoint_reopens_without_a_provider(
    tmp_path: Path, version: Literal["v1", "v2"]
) -> None:
    request = make_request(name="act", text=_TEXT, scope="Recruitment and selection", arm="test")
    live = LangGraphDiscoveryGateway(
        gateway=_BindingGateway(),
        directory=tmp_path,
        profile="fixture",
        evidence_bound=True,
        binding_version=version,
    )
    original = await live.generate(request=request)
    replay = LangGraphDiscoveryGateway(
        gateway=None,
        directory=tmp_path,
        profile="fixture",
        evidence_bound=True,
        binding_version=version,
    )
    assert await replay.generate(request=request) == original
    wrong_contract = LangGraphDiscoveryGateway(
        gateway=None, directory=tmp_path, profile="fixture", evidence_bound=False
    )
    with pytest.raises(InferenceError, match="No exact response"):
        _ = await wrong_contract.generate(request=request)


_SCREENING = "The screening tool ranks candidates."
_SCHEDULING = "The scheduling tool books interviews."


class _AliasBindingGateway(_BindingGateway):
    def __init__(self, *, witness: str, reuse: bool = False) -> None:
        super().__init__(
            extraction={
                "mentions": [
                    _mention("screen", "screening tool", _SCREENING),
                    _mention("schedule", "scheduling tool", _SCHEDULING),
                    _mention("candidate", "candidates"),
                    _mention("interview", "interviews"),
                ],
                "claims": [
                    _claim(
                        name="screening-tool",
                        title="Screening tool",
                        meaning="A tool used to rank applicants.",
                        quote=_SCREENING,
                        binding="screen",
                    ),
                    _claim(
                        name="scheduling-tool",
                        title="Scheduling tool",
                        meaning="A tool used to book interviews.",
                        quote=_SCHEDULING,
                        binding="schedule",
                    ),
                    _claim(
                        name="candidate",
                        title="Candidate",
                        meaning="A person considered for a job.",
                        quote=_SCREENING,
                        binding="candidate",
                    ),
                    _claim(
                        name="interview",
                        title="Interview",
                        meaning="A meeting with a candidate.",
                        quote=_SCHEDULING,
                        binding="interview",
                    ),
                    _claim(
                        name="ranks",
                        title="Ranks",
                        meaning=_SCREENING,
                        quote=_SCREENING,
                        binding=("screen", "candidate"),
                    ),
                    _claim(
                        name="books",
                        title="Books",
                        meaning=_SCHEDULING,
                        quote=_SCHEDULING,
                        binding=("screen" if reuse else "schedule", "interview"),
                    ),
                ],
            }
        )
        self.witness: str = witness

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        output: dict[str, object]
        if "concepts" in context:
            rows = TypeAdapter(list[dict[str, str | None]]).validate_python(context["concepts"])
            by_title = {row["title"]: row for row in rows}
            screening, scheduling = by_title["Screening tool"], by_title["Scheduling tool"]
            output = {
                "aliases": [
                    {
                        "alternate": scheduling["name"],
                        "preferred": screening["name"],
                        "alternate_quote": scheduling["quote"],
                        "preferred_quote": screening["quote"],
                        "reason": "The manual discusses both tools.",
                    }
                ]
            }
        elif "designations" in context:
            output = {"identity_witness": _anchor(self.witness)}
        else:
            return await super().generate(request=request)
        return ModelResponse(output_json=json.dumps(output), model_id="test/alias")


@pytest.mark.parametrize(
    ("witness", "merged"),
    [
        ("The screening tool and scheduling tool are the same application, HireFlow.", True),
        ("The screening tool and scheduling tool share the same application ID HR-017.", True),
        ("The screening tool and scheduling tool are the same type of application.", False),
        ("The screening tool and scheduling tool are not the same application.", False),
        (
            "The screening tool and scheduling tool export to a system also known as HireFlow.",
            False,
        ),
    ],
)
async def test_same_system_requires_an_explicit_source_witness(
    tmp_path: Path, witness: str, *, merged: bool
) -> None:
    request = make_request(
        name="manual", text=f"{_SCREENING} {_SCHEDULING} {witness}", scope="Hiring", arm="test"
    )
    graph = LangGraphDiscoveryGateway(
        gateway=_AliasBindingGateway(witness=witness),
        directory=tmp_path,
        profile="test/alias",
        binding_version="v2",
    )
    response = await graph.generate(request=request)
    output = TypeAdapter(dict[str, list[dict[str, object]]]).validate_json(response.output_json)
    first, second = output["relationships"]
    assert (first["source"] == second["source"]) is merged
    assert {first["target"], second["target"]} == {"candidate", "interview"}
    assert response.discovery_binding_json is not None
    binding = BindingEnvelope.model_validate_json(response.discovery_binding_json)
    assert (
        any(a.quote == witness for edge in binding.edges for a in edge.identity_evidence) is merged
    )


async def test_reused_label_must_be_the_mention_that_supports_the_edge(tmp_path: Path) -> None:
    witness = "The screening tool and scheduling tool are installed separately."
    request = make_request(
        name="manual", text=f"{_SCREENING} {_SCHEDULING} {witness}", scope="Hiring", arm="test"
    )
    graph = LangGraphDiscoveryGateway(
        gateway=_AliasBindingGateway(witness=witness, reuse=True),
        directory=tmp_path,
        profile="test/reused-mention",
        binding_version="v2",
    )
    response = await graph.generate(request=request)
    output = TypeAdapter(dict[str, list[dict[str, object]]]).validate_json(response.output_json)
    (ranks,) = output["relationships"]
    assert ranks["name"] == "ranks"


@pytest.mark.parametrize("explicit", [False, True])
async def test_approved_endpoint_requires_identity_and_its_revision_is_guarded(
    tmp_path: Path, *, explicit: bool
) -> None:
    action = "The applicant submits a form."
    identity = "The applicant is also known as Candidate." if explicit else "Candidates apply."
    gateway = LangGraphDiscoveryGateway(
        gateway=_BindingGateway(
            extraction={
                "mentions": [
                    {**_mention("applicant", "applicant", action), "approved_name": "candidate"},
                    _mention("form", "form"),
                ],
                "claims": [
                    _claim(
                        name="form",
                        title="Form",
                        meaning="An application form.",
                        quote=action,
                        binding="form",
                    ),
                    _claim(
                        name="submits",
                        title="Submits",
                        meaning=action,
                        quote=action,
                        binding=("applicant", "form"),
                    ),
                ],
            }
        ),
        directory=tmp_path / "audit",
        profile="test/approved",
        binding_version="v2",
    )
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway))
    project = await client.create_project(actor="reader", name="test")
    model = await project.create_model(
        actor="reader", name="recruitment", kind=ModelKind.OBSERVED, description="Recruitment"
    )
    builder = DomainModelBuilder(model_info=model.info)
    candidate = builder.add_concept(name="candidate", meaning="An applicant for a role.")
    plan = builder.build_change_plan(reason="Establish the approved Candidate concept.")
    case = await model.propose_change_plan(actor="reader", plan=plan)
    accept = Accept(reason="The proposed meaning was reviewed.")
    _ = await model.decide_review(actor="reader", case=case, decision=accept)
    current = await project.get_model(name="recruitment")
    pinned = await current.get_definition(definition_id=candidate)
    source = await project.ingest_source(
        actor="reader",
        name="policy",
        source=Statement(
            text=f"{action} {identity}",
            speaker=Person(id=PersonId(value="publisher"), name="Publisher", role="Publisher"),
            context="Policy",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    draft = await current.extract_proposals(source_revisions=[source.revision], actor="reader")
    alignment = await current.propose_alignment(actor="reader", discovery_id=draft.id)
    (binding,) = draft.relationship_bindings
    if not explicit:
        assert binding.relationship_id is None
        return
    assert binding.source is not None
    assert binding.source.definition_id == pinned.id
    assert binding.source.definition_revision == pinned.revision
    assert binding.relationship_id is not None
    assert any("also known as Candidate" in a.quote for a in binding.identity_evidence)
    cases = (await current.list_review_cases(reconciliation_id=alignment.id)).items
    (edge_case,) = (c for c in cases if c.definitions[0].id == binding.relationship_id)
    retirement = await current.propose_definition_retirement(
        actor="reader",
        definition_id=pinned.id,
        expected_revision=pinned.revision,
        reason="Retire the candidate concept ahead of review.",
    )
    _ = await current.decide_review(actor="reader", case=retirement, decision=accept)
    with pytest.raises(StaleStateError, match="revised endpoints"):
        _ = await current.preview_changes(case=edge_case, decision=accept)


_NOTICE = (
    "Before putting into service or using a high-risk system at the workplace, "
    "employer-deployers must inform workers' representatives and affected workers."
)
_CLASSIFICATION = "Under Article 6, Annex III systems are classified as high-risk."
_DEROGATION = "Article 6\nA derogation applies to qualifying Annex III systems."
_PROFILING = "Annex III systems that profile natural persons are always high-risk."


def _legislation() -> dict[str, object]:
    mentions: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    for ref, label, title in (
        ("employer", "employer-deployers", "Employer-deployer"),
        ("representative", "workers' representatives", "Workers' representatives"),
        ("worker", "affected workers", "Affected workers"),
    ):
        mentions.append(_mention(ref, label))
        claims.append(_claim(name=ref, title=title, meaning=label, quote=_NOTICE, binding=ref))
    for target in ("representative", "worker"):
        claim = _claim(
            name="informs",
            title="Informs before workplace use",
            meaning=_NOTICE,
            quote=_NOTICE,
            binding=("employer", target),
        )
        claim["modality"] = "obligation"
        claim["qualifiers"] = [
            {
                "ref": "timing",
                "applies_to": None,
                "kind": "condition",
                "text": "Before putting into service or using a high-risk system at the workplace",
                "evidence": [
                    _anchor(
                        "Before putting into service or using a high-risk system at the workplace"
                    )
                ],
            }
        ]
        claims.append(claim)
    for ref, label in (("system", "Annex III systems"), ("risk", "high-risk")):
        mention = _mention(ref, label)
        mention["anchor"] = _anchor(label, citation=2)
        mentions.append(mention)
        claim = _claim(name=ref, title=label, meaning=label, quote=_CLASSIFICATION, binding=ref)
        claim["evidence"] = [_anchor(_CLASSIFICATION, citation=2)]
        claims.append(claim)
    classification = _claim(
        name="classified-as",
        title="Classified as",
        meaning=_CLASSIFICATION,
        quote=_CLASSIFICATION,
        binding=("system", "risk"),
    )
    classification["evidence"] = [_anchor(_CLASSIFICATION, citation=2)]
    classification["qualifiers"] = [
        {
            "ref": "derogation",
            "applies_to": None,
            "kind": "exception",
            "text": "A derogation applies to qualifying Annex III systems.",
            "evidence": [_anchor(_DEROGATION.splitlines()[1], citation=3)],
        },
        {
            "ref": "profiling",
            "applies_to": "derogation",
            "kind": "override",
            "text": _PROFILING,
            "evidence": [_anchor(_PROFILING, citation=4)],
        },
    ]
    claims.append(classification)
    return {"mentions": mentions, "claims": claims}


async def test_both_recipients_and_nested_exception_reopen(tmp_path: Path) -> None:
    origin = ParsedSourceOrigin(
        document_id="act-tests",
        document_revision="1",
        provider="fixture",
        captured_at=datetime(2026, 11, 19, tzinfo=UTC),
    )
    parts = [
        ParsedText(text=value, locator=ExternalLocation(key=label))
        for label, value in (
            ("notice", _NOTICE),
            ("classification", _CLASSIFICATION),
            ("derogation", _DEROGATION),
            ("override", _PROFILING),
        )
    ]

    class Resolver(ParsedSourceResolver):
        @override
        @asynccontextmanager
        async def open(
            self,
            *,
            origin: ParsedSourceOrigin,
            limits: ProcessingLimits,
        ) -> AsyncGenerator[ParsedPayload]:
            yield ParsedPayload(origin=origin, parts=parts)

    gateway = LangGraphDiscoveryGateway(
        gateway=_RecordedGateway(extraction=_legislation()),
        directory=tmp_path / "audit",
        profile="fixture",
        evidence_bound=True,
        binding_version="v1",
    )
    client = Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=gateway),
        integrations=ClientIntegrations(
            parsed_source_providers=[ParsedSourceProvider(name="fixture", resolver=Resolver())]
        ),
    )
    project = await client.create_project(actor="reviewer", name="test")
    model = await project.create_model(
        name="act",
        actor="reviewer",
        description="Workplace notice and classification",
        kind=ModelKind.OBSERVED,
    )
    source = await project.ingest_source(
        name="act",
        actor="reviewer",
        source=ParsedSource(origin=origin, parts=parts),
    )
    draft = await model.extract_proposals(source_revisions=[source.revision], actor="reviewer")
    alignment = await model.propose_alignment(actor="reviewer", discovery_id=draft.id)
    cases = [case async for case in model.iter_review_cases(reconciliation_id=alignment.id)]
    definitions = {d.id: d for case in cases for d in case.definitions}
    recipients: set[str] = set()
    for definition in definitions.values():
        body = definition.body
        if definition.display_name != "Informs before workplace use":
            continue
        assert isinstance(body, RelationshipDefinition)
        assert isinstance(body.source_concept_id, DefinitionId)
        assert isinstance(body.target_concept_id, DefinitionId)
        assert definitions[body.source_concept_id].display_name == "Employer-deployer"
        recipients.add(definitions[body.target_concept_id].display_name)
        assert "Before putting into service or using a high-risk system" in definition.meaning
    assert recipients == {"Workers' representatives", "Affected workers"}
    (classification,) = (
        case for case in cases if any(d.name == "classified-as" for d in case.definitions)
    )
    excerpts = {
        (await project.get_evidence(evidence=anchor)).excerpt for anchor in classification.evidence
    }
    assert excerpts == {_CLASSIFICATION, _DEROGATION, _PROFILING}
    assert "Override of" in classification.definitions[0].meaning


@pytest.mark.parametrize("version", ["v1", "v2"])
async def test_repair_rebinds_the_endpoint_on_the_same_claim(
    tmp_path: Path, version: Literal["v1", "v2"]
) -> None:
    fixture = _recruitment()
    claims = TypeAdapter(list[dict[str, object]]).validate_python(fixture["claims"])
    (original,) = (claim for claim in claims if claim["name"] == "evaluates")
    unsafe = (
        {**original, "source": "c", "target": "r", "meaning": "Candidates evaluate systems."}
        if version == "v2"
        else {**original, "source": "other", "meaning": "Selection systems evaluate candidates."}
    )
    fixture["claims"] = [
        unsafe if claim["name"] == "evaluates" else claim
        for claim in claims
        if claim["name"] != "reverse-evaluation"
    ]

    class RepairGateway(_BindingGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            context = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
            response = await super().generate(request=request)
            if "disputed_claims" in context:
                (item,) = TypeAdapter(list[dict[str, dict[str, object] | str]]).validate_python(
                    context["disputed_claims"]
                )
                disputed = item["claim"]
                assert isinstance(disputed, dict)
                return ModelResponse(
                    output_json=json.dumps(
                        {
                            "mentions": fixture["mentions"],
                            "claims": [{**original, "claim_id": disputed["claim_id"]}],
                        }
                    ),
                    model_id="test/evidence-bound",
                )
            if "claims" in context:
                rows = TypeAdapter(list[dict[str, object]]).validate_python(context["claims"])
                verdicts = [
                    {
                        "index": index,
                        "status": "partly_supported"
                        if row["meaning"] == unsafe["meaning"]
                        else "supported",
                        "reason": "Read the participant in its cited sentence.",
                    }
                    for index, row in enumerate(rows)
                ]
                return ModelResponse(
                    output_json=json.dumps({"verdicts": verdicts}), model_id="test/evidence-bound"
                )
            return response

    request = make_request(name="act", text=_TEXT, scope="Recruitment and selection", arm="repair")
    gateway = LangGraphDiscoveryGateway(
        gateway=RepairGateway(extraction=fixture),
        directory=tmp_path,
        profile="fixture",
        evidence_bound=True,
        binding_version=version,
    )
    response = await gateway.generate(request=request)
    report = TypeAdapter(dict[str, object]).validate_json(
        next((tmp_path / request.request_id).glob("*.json")).read_bytes()
    )
    (batch,) = TypeAdapter(list[BatchResult]).validate_python(report["batches"])
    (disputed,) = (c for c in batch.candidates if c.meaning == unsafe["meaning"])
    (repaired,) = (c for c in batch.accepted if c.name == "evaluates")
    assert isinstance(disputed, BoundClaim)
    assert disputed.subject is not None
    assert isinstance(repaired, BoundClaim)
    assert repaired.subject is not None
    assert repaired.claim_id == disputed.claim_id
    assert repaired.subject.id != disputed.subject.id
    assert repaired.subject.anchor.quote == "Recruitment systems"
    if version == "v2":
        assert response.discovery_binding_json is not None
        (edge,) = BindingEnvelope.model_validate_json(response.discovery_binding_json).edges
        assert edge.previous_source is not None
        assert edge.previous_source.occurrence.anchor.quote == "candidates"
        assert edge.previous_target is not None
        assert edge.previous_target.occurrence.anchor.quote == "Recruitment systems"
