"""Exercise schema discovery through the public workflow with scripted receipts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, override

import pytest
from pydantic import TypeAdapter

from domain_kernel import (
    Client,
    ClientConfiguration,
    CompetencyQuestion,
    ConceptDefinition,
    InferenceError,
    LangGraphDiscoveryGateway,
    MissingCapabilityError,
    ModelGateway,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackSpec,
    RelationshipDefinition,
    RunStatus,
    SchemaDiscoveryOptions,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel.configuration import InferencePolicy
from domain_kernel.discovery.application import extraction

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Model, SourceRevision

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SAMPLE = "Work order WO-17 references machine M-03."


async def _workspace(  # noqa: PLR0913 - Script the captured inference messages and retry behavior.
    *,
    path: Path,
    gateway: ModelGateway,
    reference_pack: ReferencePack | None = None,
    texts: tuple[str, ...] = (_SAMPLE,),
    description: str = "Describe machine maintenance work orders.",
    proposal_limit: int | None = None,
    inference: InferencePolicy | None = None,
) -> tuple[Model, list[SourceRevision]]:
    client = Client(
        config=ClientConfiguration(
            base_dir=path,
            model_gateway=gateway,
            inference=inference
            or (
                InferencePolicy(max_proposals=proposal_limit)
                if proposal_limit is not None
                else InferencePolicy()
            ),
        )
    )
    project = await client.create_project(name="maintenance", actor="expert")
    model = await project.create_model(
        name="work",
        description=description,
        kind=ModelKind.PROPOSED,
        actor="expert",
        reference_pack=reference_pack,
    )
    captures = [
        await project.ingest_source(
            name=f"source-{index}",
            actor="expert",
            source=Statement(
                text=text,
                speaker=Person(id=PersonId(value="owner"), name="Lee", role="Owner"),
                context="Maintenance documents",
                form=StatementForm.QUOTATION,
                intent=StatementIntent.ASSERTION,
            ),
        )
        for index, text in enumerate(texts)
    ]
    sources = [item.revision for item in captures]
    return model, sources


class _WholeQuestionGateway(ModelGateway):
    supports_schema_discovery: bool = True

    def __init__(self, *, mode: str) -> None:
        super().__init__()
        self.mode: str = mode
        self.stages: list[str | None] = []
        self.scopes: list[list[str]] = []
        self.draft_bytes: int = 0
        self.draft_limit: object = None
        self.draft_output_bytes: int | None = None
        self.draft_timeout: float | None = None

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        stage = request.provider_stage
        self.stages.append(stage)
        frame = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
        fact: dict[str, object] = {
            "question_ids": ["purpose" if self.mode == "default" else "work"],
            "witnesses": ["E1.1"],
            "modality": "descriptive",
            "qualifiers": [],
            "applicability": "The reported case.",
        }
        concepts = [
            {
                **fact,
                "name": name,
                "display_name": name.title(),
                "meaning": f"The {name.replace('-', ' ')} in the report.",
            }
            for name in ("work-order", "machine")
        ]
        edge: dict[str, object] = {
            **fact,
            "name": "references-machine",
            "display_name": "references",
            "meaning": "The work order references the machine.",
            "source": "work-order",
            "target": "machine",
            "record_binding": None,
        }
        has_link = self.mode in (
            "default",
            "complete",
            "long",
            "unresolved",
            "unavailable-review",
            "missing-example",
            "missing-example-unissued",
            "missing-example-wrong-link",
        )
        if stage == "schema-compact-orientation":
            assert self.mode == "long"
            reply: dict[str, object] = {
                "entries": [],
                "focus": [
                    {"question_id": key, "queries": ["machine"], "passages": [1]}
                    for key in ("work", "machine")
                ],
            }
        elif stage == "schema-compact-draft":
            assert "facet_plan" not in frame
            self.draft_bytes = sum(len(part.text.encode()) for part in request.inputs)
            self.draft_limit = frame["review_limit"]
            self.draft_output_bytes = request.discovery_output_bytes
            self.draft_timeout = request.timeout_seconds
            reply = {
                "concepts": concepts,
                "relationships": [edge] if has_link else [],
                "questions": [],
                "unresolved_facets": [],
            }
        else:
            assert stage == "schema-compact-repair"
            scope = TypeAdapter(dict[str, str]).validate_python(frame.get("question_scope"))
            self.scopes.append(list(scope))
            if self.mode == "unavailable-review":
                raise InferenceError(message="The review call did not return.")
            targeted = frame.get("review_pass") == "targeted"
            if targeted and self.mode == "unavailable-repair":
                raise InferenceError(message="The targeted repair call did not return.")
            adds_link = targeted or self.mode == "bad-check"
            expected_link = {k: edge[k] for k in ("name", "source", "target")}
            if self.mode == "missing-example-wrong-link":
                expected_link["source"], expected_link["target"] = (
                    expected_link["target"],
                    expected_link["source"],
                )
            link_check = {
                "facet_id": 1,
                "example": None if self.mode.startswith("missing-") else _SAMPLE,
                "contrast": None,
                "status": "supported" if has_link or adds_link else "missing_model",
                "concepts": ["work-order", "machine"],
                "links": [expected_link | {"condition_slots": list[int]()}],
                "witnesses": ["E1.99"] if self.mode == "missing-example-unissued" else ["E1.1"],
                "reason": "The report names the machine referenced by this work order.",
            }
            other_check = {
                "facet_id": 2,
                "example": _SAMPLE,
                "contrast": None,
                "status": "insufficient" if self.mode == "unresolved" else "supported",
                "concepts": ["machine"],
                "links": [],
                "witnesses": ["E1.99"] if self.mode == "bad-check" else ["E1.1"],
                "reason": "This excerpt does not determine a machine policy.",
            }
            reply = {
                "upsert": {
                    "concepts": [],
                    "relationships": [edge] if adds_link else [],
                    "questions": [],
                },
                "drop": [],
                "label_edits": [],
                "label_flags": [],
                "checks": (
                    [link_check]
                    if targeted or self.mode == "default"
                    else [link_check, other_check]
                ),
            }
        return ModelResponse(model_id="test/whole-questions", output_json=json.dumps(reply))


@pytest.mark.parametrize("proposal_limit", [None, 10])
async def test_discover_defaults_to_whole_question_review(
    tmp_path: Path, *, proposal_limit: int | None
) -> None:
    gateway = _WholeQuestionGateway(mode="default")
    model, sources = await _workspace(path=tmp_path, gateway=gateway, proposal_limit=proposal_limit)
    run = await model.discover(actor="expert", sources=sources, idempotency_key="default")

    assert gateway.stages == ["schema-compact-draft", "schema-compact-repair"]
    assert gateway.scopes == [["purpose"]]
    assert gateway.draft_limit == (proposal_limit if proposal_limit is not None else 128)
    assert gateway.draft_output_bytes == 512 * 1024
    stage_timeout_seconds = 600.0
    assert gateway.draft_timeout == stage_timeout_seconds
    assert not run.failures
    repeated = await model.discover(actor="expert", sources=sources, idempotency_key="default")
    assert repeated == run
    assert gateway.stages == ["schema-compact-draft", "schema-compact-repair"]


@pytest.mark.parametrize("size", [512 * 1024, 512 * 1024 + 1])
async def test_public_discovery_enforces_the_response_byte_boundary(
    tmp_path: Path, *, size: int
) -> None:
    class PaddedDraft(_WholeQuestionGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            result = await super().generate(request=request)
            if request.provider_stage == "schema-compact-draft":
                payload = result.output_json
                return ModelResponse(model_id=result.model_id, output_json=payload.ljust(size))
            return result

    gateway = PaddedDraft(mode="default")
    model, sources = await _workspace(path=tmp_path, gateway=gateway)
    run = await model.discover(actor="expert", sources=sources)
    limit = 512 * 1024
    if size == limit:
        assert run.status is RunStatus.NEEDS_REVIEW
        assert gateway.stages == ["schema-compact-draft", "schema-compact-repair"]
    else:
        assert run.status is RunStatus.FAILED
        assert run.discovery_id is None
        assert "output budget" in run.failures[0].issue.message
        assert "schema-compact-repair" not in gateway.stages


@pytest.mark.parametrize("count", [128, 129])
async def test_public_discovery_enforces_the_item_boundary(tmp_path: Path, *, count: int) -> None:
    class ManyMeanings(_WholeQuestionGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            result = await super().generate(request=request)
            if request.provider_stage != "schema-compact-draft":
                return result
            body = TypeAdapter(dict[str, object]).validate_json(result.output_json)
            concepts = TypeAdapter(list[dict[str, object]]).validate_python(body["concepts"])
            extras = [
                {**concepts[0], "name": f"fixture-type-{number}"}
                for number in range(count - len(concepts) - 1)
            ]
            return ModelResponse(
                model_id=result.model_id,
                output_json=json.dumps({**body, "concepts": [*concepts, *extras]}),
            )

    gateway = ManyMeanings(mode="default")
    model, sources = await _workspace(path=tmp_path, gateway=gateway)
    run = await model.discover(actor="expert", sources=sources)
    limit = 128
    if count == limit:
        assert run.status is RunStatus.NEEDS_REVIEW
        assert gateway.stages == ["schema-compact-draft", "schema-compact-repair"]
    else:
        assert run.status is RunStatus.FAILED
        assert run.discovery_id is None
        assert "review limit" in run.failures[0].issue.message
        assert "schema-compact-repair" not in gateway.stages


@pytest.mark.parametrize(
    ("total_seconds", "expected_timeouts"),
    [(None, [600.0, 600.0, 600.0, 600.0]), (950.0, [600.0, 350.0])],
)
async def test_discovery_spends_one_inference_budget_across_attempts_and_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    total_seconds: float | None,
    expected_timeouts: list[float],
) -> None:
    clock = 0.0

    def monotonic() -> float:
        return clock

    class SlowDraft(_WholeQuestionGateway):
        def __init__(self) -> None:
            super().__init__(mode="default")
            self.timeouts: list[float] = []

        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            nonlocal clock
            assert request.provider_stage == "schema-compact-draft"
            self.timeouts.append(request.timeout_seconds)
            clock += request.timeout_seconds
            if len(self.timeouts) < len(expected_timeouts):
                raise InferenceError(message="Draft timed out.", retryable=True)
            return await super().generate(request=request)

    monkeypatch.setattr(extraction, "monotonic", monotonic)
    gateway = SlowDraft()
    model, sources = await _workspace(
        path=tmp_path,
        gateway=gateway,
        inference=InferencePolicy(timeout_seconds=total_seconds) if total_seconds else None,
    )
    run = await model.discover(actor="expert", sources=sources)
    assert gateway.timeouts == expected_timeouts
    assert clock == (total_seconds or 2400.0)
    assert run.status is RunStatus.PARTIALLY_FAILED
    assert run.discovery_id is not None
    assert [case async for case in model.iter_review_cases(run_id=run.id)]


@pytest.mark.parametrize("target", ["E1.3", "E1.6"])
async def test_public_discovery_keeps_ordered_roles_inside_one_record(
    tmp_path: Path, *, target: str
) -> None:
    class SeparateFields(_WholeQuestionGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            result = await super().generate(request=request)
            if request.provider_stage != "schema-compact-draft":
                return result
            assert "[E1.2] Work order: WO-17" in request.inputs[0].text
            assert "[E1.3] Machine: M-03" in request.inputs[0].text
            assert "[E1.6] Machine: M-12" in request.inputs[0].text
            body = TypeAdapter(dict[str, object]).validate_json(result.output_json)
            (edge,) = TypeAdapter(list[dict[str, object]]).validate_python(body["relationships"])
            edge.update(
                record_binding={"anchor": "E1.1", "source": "E1.2", "target": target},
                witnesses=["E1.1", "E1.2", target],
            )
            return ModelResponse(
                model_id=result.model_id, output_json=json.dumps({**body, "relationships": [edge]})
            )

    gateway = SeparateFields(mode="default")
    model, sources = await _workspace(
        path=tmp_path,
        gateway=gateway,
        texts=(
            (
                "# Entry A\nWork order: WO-17\nMachine: M-03\n"
                "# Entry B\nWork order: WO-18\nMachine: M-12"
            ),
        ),
    )
    run = await model.discover(actor="expert", sources=sources)
    cases = [case async for case in model.iter_review_cases(run_id=run.id)]
    concepts = {d.name: d for case in cases for d in case.definitions}
    if target == "E1.3":
        edge = concepts["references-machine"].body
        assert isinstance(edge, RelationshipDefinition)
        assert edge.source_concept_id == concepts["work-order"].id
        assert edge.target_concept_id == concepts["machine"].id
    else:
        assert "references-machine" not in concepts
        assert run.status is RunStatus.PARTIALLY_FAILED


@pytest.mark.parametrize(
    ("mode", "targeted", "link", "partial"),
    [
        ("complete", False, True, False),
        ("missing-example", False, True, False),
        ("missing-example-unissued", False, True, True),
        ("missing-example-wrong-link", False, True, True),
        ("missing-gap-example", False, False, True),
        ("targeted", True, True, False),
        ("unresolved", False, True, False),
        ("bad-check", False, True, True),
        ("unavailable-review", False, True, True),
        ("unavailable-repair", True, False, True),
    ],
)
async def test_question_led_review_reopens_only_a_grounded_missing_link(
    tmp_path: Path, *, mode: str, targeted: bool, link: bool, partial: bool
) -> None:
    gateway = _WholeQuestionGateway(mode=mode)
    model, sources = await _workspace(path=tmp_path, gateway=gateway, texts=(_SAMPLE,))
    run = await model.discover(
        actor="expert",
        sources=sources,
        schema_options=SchemaDiscoveryOptions(
            competency_questions=(
                CompetencyQuestion(id="work", text="What does the work order reference?"),
                CompetencyQuestion(id="machine", text="How is the machine represented?"),
            ),
        ),
    )
    assert gateway.stages == ["schema-compact-draft", *["schema-compact-repair"] * (1 + targeted)]
    assert gateway.scopes == (
        [["work", "machine"], ["work"]] if targeted else [["work", "machine"]]
    )
    assert bool(run.failures) is partial
    assert (
        any(
            [
                case.definitions[0].name == "references-machine"
                async for case in model.iter_review_cases(run_id=run.id)
            ]
        )
        is link
    )


@pytest.mark.parametrize("on_relationship", [True, False])
async def test_question_review_requires_the_qualifier_on_the_cited_relationship(
    tmp_path: Path, *, on_relationship: bool
) -> None:
    qualifier = "Only after the supervisor signs."
    sample = "Work order WO-17 references machine M-03 only after the supervisor signs."

    class QualificationGateway(_WholeQuestionGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            result = await super().generate(request=request)
            body = TypeAdapter(dict[str, object]).validate_json(result.output_json)
            if request.provider_stage == "schema-compact-draft":
                key = "relationships" if on_relationship else "concepts"
                rows = TypeAdapter(list[dict[str, object]]).validate_python(body[key])
                rows[0]["qualifiers"] = [qualifier]
                body[key] = rows
            else:
                (check,) = TypeAdapter(list[dict[str, object]]).validate_python(body["checks"])
                (link,) = TypeAdapter(list[dict[str, object]]).validate_python(check["links"])
                check.update(example=sample, links=[{**link, "condition_slots": [2]}])
                body["checks"] = [check]
            return ModelResponse(model_id=result.model_id, output_json=json.dumps(body))

    gateway = QualificationGateway(mode="default")
    model, sources = await _workspace(path=tmp_path, gateway=gateway, texts=(sample,))
    run = await model.discover(actor="expert", sources=sources)

    expected_status = RunStatus.NEEDS_REVIEW if on_relationship else RunStatus.PARTIALLY_FAILED
    assert run.status is expected_status
    assert gateway.stages == ["schema-compact-draft", "schema-compact-repair"]
    assert "references-machine" in {
        definition.name
        async for case in model.iter_review_cases(run_id=run.id)
        for definition in case.definitions
    }


async def test_question_led_drafting_bounds_long_evidence_without_generating_facets(
    tmp_path: Path,
) -> None:
    gateway = _WholeQuestionGateway(mode="long")
    model, sources = await _workspace(
        path=tmp_path,
        gateway=gateway,
        texts=(
            _SAMPLE,
            "Routine machine maintenance is logged.\n" * 550,
            "The work order is used for routine maintenance.\n" * 450,
            "Report the date of work order delivery.\n" * 550,
        ),
    )
    run = await model.discover(
        actor="expert",
        sources=sources,
        schema_options=SchemaDiscoveryOptions(
            competency_questions=(
                CompetencyQuestion(id="work", text="What does the work order reference?"),
                CompetencyQuestion(id="machine", text="How is the machine represented?"),
            ),
        ),
    )
    assert gateway.stages == [
        "schema-compact-orientation",
        "schema-compact-draft",
        "schema-compact-repair",
    ]
    projected_ceiling = 60_000
    assert 0 < gateway.draft_bytes <= projected_ceiling
    assert gateway.scopes == [["work", "machine"]]
    assert not run.failures


async def test_v23_restarts_partial_review_without_losing_its_run(
    tmp_path: Path,
) -> None:
    gateway = _WholeQuestionGateway(mode="unavailable-review")
    model, sources = await _workspace(path=tmp_path, gateway=gateway)
    options = SchemaDiscoveryOptions(
        competency_questions=(
            CompetencyQuestion(id="work", text="What does the work order reference?"),
            CompetencyQuestion(id="machine", text="How is the machine represented?"),
        ),
    )
    partial = await model.discover(actor="expert", sources=sources, schema_options=options)
    assert partial.status is RunStatus.PARTIALLY_FAILED
    assert partial.discovery_id is not None
    assert [case async for case in model.iter_review_cases(run_id=partial.id)]

    restarted = _WholeQuestionGateway(mode="complete")
    client = Client(config=ClientConfiguration(base_dir=tmp_path, model_gateway=restarted))
    project = await client.get_project(name="maintenance")
    reopened = await project.get_model(name="work")
    complete = await reopened.resume_discovery(actor="expert", run_id=partial.id)
    assert complete.id == partial.id
    assert complete.prompt == partial.prompt
    assert complete.status is RunStatus.NEEDS_REVIEW
    assert not complete.failures


@pytest.mark.parametrize("mapping_available", [True, False])
async def test_v23_maps_after_local_review_and_preserves_draft_if_deferred(
    tmp_path: Path, *, mapping_available: bool
) -> None:
    class MappingGateway(_WholeQuestionGateway):
        def __init__(self) -> None:
            super().__init__(mode="default")
            self.calls: int = 0

        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            if request.provider_stage != "schema-mapping":
                assert "Serialized hardware maintained at a site." not in (
                    request.context_json or ""
                )
                return await super().generate(request=request)
            self.stages.append(request.provider_stage)
            self.calls += 1
            frame = TypeAdapter(dict[str, object]).validate_json(request.context_json or "{}")
            assert "pairs" in frame
            assert request.inputs[0].text == _SAMPLE
            if self.calls == 1 or not mapping_available:
                raise InferenceError(message="Mapping provider unavailable.", retryable=True)
            return ModelResponse(
                model_id="test/mapping",
                output_json=(
                    '{"suggestions":[{"pair":1,"relation":"related",'
                    '"reason":"The work order concerns maintained hardware."}]}'
                ),
            )

    build = ReferencePack.compose(
        actor="expert",
        reason="Compare with a pinned manufacturing term.",
        spec=ReferencePackSpec(
            key="example.manufacturing",
            version="1.0.0",
            title="Manufacturing terms",
            applicability="Hardware maintenance.",
            provenance="Authored for the fixture.",
            license="Apache-2.0",
            definitions=[
                ReferenceDefinition(
                    id=ReferenceDefinitionId(value="hardware"),
                    name="hardware",
                    meaning="Serialized hardware maintained at a site.",
                    body=ConceptDefinition(),
                    provenance="Authored for the fixture.",
                )
            ],
        ),
    )
    assert build.pack is not None
    gateway = MappingGateway()
    model, sources = await _workspace(path=tmp_path, gateway=gateway, reference_pack=build.pack)
    run = await model.discover(actor="expert", sources=sources)
    assert gateway.stages[:2] == ["schema-compact-draft", "schema-compact-repair"]
    expected_mapping_calls = 2 if mapping_available else 4
    assert gateway.stages[2:] == ["schema-mapping"] * expected_mapping_calls
    expected_status = RunStatus.NEEDS_REVIEW if mapping_available else RunStatus.PARTIALLY_FAILED
    assert run.status is expected_status
    assert run.discovery_id is not None
    cases = [case async for case in model.iter_review_cases(run_id=run.id)]
    assert {d.name for case in cases for d in case.definitions} == {
        "work-order",
        "machine",
        "references-machine",
    }
    if not mapping_available:
        assert any("mapping" in item.issue.message for item in run.failures)


async def test_discover_rejects_a_standalone_only_gateway_before_persisting_run(
    tmp_path: Path,
) -> None:
    class StandaloneOnly(ModelGateway):
        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            raise AssertionError("An unsupported discovery call must not reach inference.")

    model, sources = await _workspace(path=tmp_path, gateway=StandaloneOnly())
    with pytest.raises(MissingCapabilityError, match="structured schema discovery"):
        _ = await model.discover(actor="expert", sources=sources)
    assert not (await model.list_discovery_runs()).items


@pytest.mark.parametrize(("host_attempts", "draft_calls"), [(None, 4), (2, 2)])
async def test_langgraph_uses_v23_retry_budget_but_does_not_retry_review(
    tmp_path: Path, *, host_attempts: int | None, draft_calls: int
) -> None:
    expected_default_attempts = 4

    class RetryableStages(_WholeQuestionGateway):
        def __init__(self) -> None:
            super().__init__(mode="default")
            self.calls: list[tuple[str | None, float]] = []

        @override
        async def generate(self, *, request: ModelRequest) -> ModelResponse:
            self.calls.append((request.provider_stage, request.timeout_seconds))
            if (
                len(self.calls) < expected_default_attempts
                or request.provider_stage == "schema-compact-repair"
            ):
                raise InferenceError(message="Try again.", retryable=True)
            return await super().generate(request=request)

    provider = RetryableStages()
    gateway = LangGraphDiscoveryGateway(
        gateway=provider,
        profile="test-v23",
        directory=tmp_path / "journal",
        stage_timeout_seconds=30.0,
    )
    model, sources = await _workspace(
        path=tmp_path,
        gateway=gateway,
        inference=InferencePolicy(max_attempts=host_attempts) if host_attempts else None,
    )
    run = await model.discover(actor="expert", sources=sources)
    if host_attempts is None:
        assert run.status is RunStatus.PARTIALLY_FAILED
        assert [case async for case in model.iter_review_cases(run_id=run.id)]
    else:
        assert run.status is RunStatus.FAILED
        assert not [case async for case in model.iter_review_cases(run_id=run.id)]
    assert provider.calls == [
        *[("schema-compact-draft", 30.0)] * draft_calls,
        *([("schema-compact-repair", 30.0)] if host_attempts is None else []),
    ]
