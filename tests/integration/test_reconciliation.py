"""Exercise the separate source and reference review queues against exact snapshots."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, final

import pytest

from domain_kernel import (
    Accept,
    AlignmentLayer,
    AlignmentStatus,
    CaseKind,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DomainModelBuilder,
    InvalidDecisionError,
    MappingRelation,
    MapToDefinition,
    MapToPlannedDefinition,
    ModelKind,
    ModelRequest,
    ModelResponse,
    ObligationId,
    ObligationKind,
    Person,
    PersonId,
    RapidFuzzSimilarityScorer,
    ReferenceDefinition,
    ReferenceDefinitionId,
    ReferencePack,
    ReferencePackObligation,
    ReferencePackSpec,
    Reject,
    StaleStateError,
    Statement,
    StatementForm,
    StatementIntent,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import (
        AlignmentId,
        DiscoveryRunId,
        IngestedSource,
        Model,
        Project,
        ReviewCase,
    )

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_EXPECTED_CASES = 3
_PASSAGE = "Part in the inventory ledger means a serialized physical unit."
_OUTPUT = (
    '{"concepts":[{"name":"part","display_name":"Part",'
    '"meaning":"A serialized physical unit.","citations":[1],"confidence":null},'
    '{"name":"serial-number","display_name":"Serial number",'
    '"meaning":"Identifier attached to a physical unit.","citations":[1],"confidence":null}],'
    '"relationships":[]}'
)


@final
class _Gateway:
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        assert request.inputs[0].text == _PASSAGE
        return ModelResponse(output_json=_OUTPUT, model_id="authored/inventory")


def _pack() -> ReferencePack:
    item = ReferenceDefinition(
        id=ReferenceDefinitionId(value="manufactured-item"),
        name="manufactured-item",
        meaning="Any separately identifiable item made or supplied for a production process.",
        body=ConceptDefinition(),
        provenance="Curated manufacturing reference.",
    )
    pack = ReferencePack.compose(
        actor="pack-editor",
        reason="Provide a wider manufacturing category.",
        spec=ReferencePackSpec(
            key="example.manufacturing",
            version="1.0.0",
            title="Manufacturing vocabulary",
            applicability="Manufacturer item identity.",
            provenance="Authored examples.",
            license="Apache-2.0",
            definitions=[item],
            obligations=[
                ReferencePackObligation(
                    id=ObligationId(value="manufactured-item-coverage"),
                    description="Review coverage for the manufactured item.",
                    kind=ObligationKind.COVERAGE,
                    required=True,
                    reference_ids=[item.id],
                    validator_id="domain-kernel.coverage@1.0",
                ),
            ],
        ),
    ).pack
    assert pack is not None
    return pack


async def _capture(*, project: Project) -> IngestedSource:
    return await project.ingest_source(
        actor="editor",
        name="inventory-clarification",
        source=Statement(
            text=_PASSAGE,
            speaker=Person(id=PersonId(value="operator"), name="Mina", role="Operator"),
            context="Warehouse terminology.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )


async def _paged_cases(
    *, model: Model, alignment_id: AlignmentId, run_id: DiscoveryRunId
) -> tuple[ReviewCase, ...]:
    page = await model.list_review_cases(
        reconciliation_id=alignment_id,
        run_id=run_id,
        status=CaseStatus.PENDING,
        limit=1,
    )
    other = await model.list_review_cases(
        reconciliation_id=alignment_id,
        run_id=run_id,
        status=CaseStatus.PENDING,
        limit=10,
        cursor=page.next_cursor,
    )
    cases = (*page.items, *other.items)
    assert len(cases) == _EXPECTED_CASES
    assert page.next_cursor is not None
    with pytest.raises(ValueError, match="same query"):
        _ = await model.list_review_cases(reconciliation_id=alignment_id, cursor=page.next_cursor)
    return cases


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("same_as", MappingRelation.EQUIVALENT),
        ("narrower_than", MappingRelation.NARROWER),
        ("broader_than", MappingRelation.BROADER),
        ("related_to", MappingRelation.RELATED),
        ("distinct_from", MappingRelation.DISTINCT),
    ],
)
async def test_persist_both_layers_for_separate_review(
    tmp_path: Path,
    method: str,
    expected: MappingRelation,
) -> None:
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=_Gateway()),
    ).create_project(actor="editor", name="manufacturing")
    pack = _pack()
    model = await project.create_model(
        actor="editor",
        name="inventory",
        kind=ModelKind.OBSERVED,
        description="Inventory distinguishes catalogue types and physical items.",
        reference_pack=pack,
    )
    prior = await model.propose_definition(
        actor="editor",
        display_name="Catalog item",
        aliases=["Part", "Manufactured item"],
        meaning="A catalog type designating interchangeable manufactured items.",
        body=ConceptDefinition(),
        reason="Preserve the procurement meaning.",
    )
    _ = await model.decide_review(
        actor="reviewer",
        case=prior,
        decision=Accept(reason="Approve the catalog meaning."),
    )
    definition = await model.get_definition(name="catalog-item")
    capture = await _capture(project=project)
    draft = await model.extract_proposals(actor="editor", source_revisions=[capture.revision])
    alignment = await model.propose_alignment(actor="editor", discovery_id=draft.id)
    assert alignment.status is AlignmentStatus.PREPARED
    assert alignment.reference_pack == pack.pin
    source = next(x for x in alignment.suggestions if x.layer is AlignmentLayer.SOURCE_TO_MODEL)
    target = next(x for x in alignment.suggestions if x.layer is AlignmentLayer.MODEL_TO_REFERENCE)
    assert source.definition_id == target.definition_id == definition.id
    assert source.evidence == draft.proposals[0].evidence
    assert source.relation is None
    assert target.reference_id == pack.definitions[0].id
    assert target.relation is None
    assert tuple(alignment.unmatched_proposal_ids) == (draft.proposals[1].id,)
    assert tuple(alignment.uncovered_reference_ids) == (pack.definitions[0].id,)

    offline_project = await Client(
        config=ClientConfiguration(base_dir=tmp_path),
    ).get_project(name=project.name)
    offline = await offline_project.get_model(name=model.info.name)
    assert await offline.get_alignment(alignment_id=alignment.id) == alignment
    assert await offline.propose_alignment(actor="editor", discovery_id=draft.id) == alignment
    cases = await _paged_cases(model=offline, alignment_id=alignment.id, run_id=draft.run_id)
    source_case = next(
        x
        for x in cases
        if x.kind is CaseKind.SOURCE_ALIGNMENT and x.proposal_ids == source.proposal_ids
    )
    reference_case = next(x for x in cases if x.kind is CaseKind.REFERENCE_ALIGNMENT)
    assert source_case.evidence == source.evidence
    _ = await offline.decide_review(
        actor="reviewer",
        case=source_case,
        decision=Reject(reason="This occurrence denotes a physical unit."),
    )
    review_factories = {
        "same_as": reference_case.same_as,
        "narrower_than": reference_case.narrower_than,
        "broader_than": reference_case.broader_than,
        "related_to": reference_case.related_to,
        "distinct_from": reference_case.distinct_from,
    }
    decision = review_factories[method](
        local_definition=definition,
        reference_definition=pack.definitions[0],
        reason="Record the independently reviewed business relation.",
    )
    impact = await offline.preview_changes(case=reference_case, decision=decision)
    assert impact.definition_changes == ()
    decision_receipt = await offline.decide_review(
        actor="reviewer", case=reference_case, decision=decision
    )
    bundle = await offline.compile(actor="reviewer")
    assert bundle.content.reference_dispositions[0].alignment is not None
    assert bundle.content.reference_dispositions[0].alignment.relation is expected
    assert await offline.get_definition(name="catalog-item") == definition
    assert tuple(bundle.content.definitions) == (definition,)

    new_draft = await model.extract_proposals(actor="editor", source_revisions=[capture.revision])
    new_alignment = await model.propose_alignment(actor="editor", discovery_id=new_draft.id)
    reused = next(
        x for x in new_alignment.suggestions if x.layer is AlignmentLayer.MODEL_TO_REFERENCE
    )
    assert reused.reused_decision_id == decision_receipt.decision_id
    assert reused.relation is expected
    assert reused.context_fingerprint == target.context_fingerprint
    if expected in (MappingRelation.EQUIVALENT, MappingRelation.NARROWER):
        assert new_alignment.uncovered_reference_ids == ()
    else:
        assert new_alignment.uncovered_reference_ids == (pack.definitions[0].id,)


async def test_no_pack_skips_the_reference_layer(tmp_path: Path) -> None:
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=_Gateway()),
    ).create_project(actor="editor", name="manufacturing")
    capture = await _capture(project=project)
    no_pack_model = await project.create_model(
        actor="editor",
        name="unassisted",
        kind=ModelKind.OBSERVED,
        description="Inventory without a selected pack.",
    )
    no_pack_draft = await no_pack_model.extract_proposals(
        actor="editor",
        source_revisions=[capture.revision],
    )
    no_pack = await no_pack_model.propose_alignment(actor="editor", discovery_id=no_pack_draft.id)
    assert no_pack.reference_pack is None
    assert no_pack.suggestions == ()
    assert no_pack.uncovered_reference_ids == ()


async def test_rapidfuzz_scorer_uses_normalized_lexical_similarity() -> None:
    scorer = RapidFuzzSimilarityScorer()
    assert scorer.score(left="catalog part", right="catalog part") == 1.0
    assert scorer.score(left="serial number", right="serial numbers") > scorer.score(
        left="serial number",
        right="asset",
    )
    assert scorer.score(left="abc", right="xyz") == 0.0


async def test_reopen_one_occurrence_preserves_prior_and_unaffected_choices(tmp_path: Path) -> None:
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=_Gateway()),
    ).create_project(actor="editor", name="manufacturing")
    model = await project.create_model(
        actor="editor",
        name="corrections",
        kind=ModelKind.OBSERVED,
        description="Separate catalog items, physical units and serial tags.",
    )
    for name in ("catalog-item", "physical-unit", "serial-tag"):
        proposed = await model.propose_definition(
            actor="editor",
            name=name,
            meaning=f"Approved local meaning for {name}.",
            body=ConceptDefinition(),
            reason="Provide a reviewed inventory vocabulary.",
        )
        _ = await model.decide_review(
            case=proposed,
            decision=Accept(reason="Approve the vocabulary term."),
            actor="reviewer",
        )
    capture = await _capture(project=project)
    draft = await model.extract_proposals(actor="editor", source_revisions=[capture.revision])
    alignment = await model.propose_alignment(actor="editor", discovery_id=draft.id)
    cases = (await model.list_review_cases(reconciliation_id=alignment.id)).items
    part = next(case for case in cases if case.definitions[0].name == "part")
    unrelated = next(case for case in cases if case.definitions[0].name == "serial-number")
    catalog = await model.get_concept(name="catalog-item")
    serial = await model.get_concept(name="serial-tag")
    mistaken = await model.decide_review(
        case=part,
        decision=part.same_as(definition=catalog, reason="The source calls it a part."),
        actor="reviewer",
    )
    _ = await model.decide_review(
        case=unrelated,
        decision=unrelated.same_as(definition=serial, reason="This describes the serial tag."),
        actor="reviewer",
    )
    before = await model.compile(actor="reviewer")
    correction = await model.reopen_review_case(
        actor="reviewer",
        case_id=part.id,
        expected_version=mistaken.case_version,
        proposal_ids=[part.proposal_ids[0]],
        reason="The inventory meaning refers to the serialized physical unit.",
    )
    with pytest.raises(InvalidDecisionError, match="overlapping"):
        _ = await model.reopen_review_case(
            actor="reviewer",
            case_id=part.id,
            expected_version=mistaken.case_version,
            proposal_ids=part.proposal_ids,
            reason="An overlapping correction would address the same occurrence.",
        )
    _ = await model.decide_review(
        case=correction,
        actor="reviewer",
        decision=Reject(reason="Keep the earlier interpretation."),
    )
    declined = await model.compile(actor="reviewer")
    assert declined.content.source_alignments == before.content.source_alignments
    correction = await model.reopen_review_case(
        actor="reviewer",
        case_id=part.id,
        expected_version=mistaken.case_version,
        proposal_ids=part.proposal_ids,
        reason="Review the precise physical meaning again.",
    )
    revised = await model.get_concept(name="physical-unit")
    choice = correction.same_as(
        definition=revised,
        reason="Review the exact inventory occurrence.",
    )
    impact = await model.preview_changes(case=correction, decision=choice)
    assert impact.definition_changes == ()
    assert impact.affected_case_ids == (correction.id, part.id)
    (difference,) = impact.source_alignment_changes
    assert difference.before is not None
    assert difference.before.definition_id == catalog.id
    assert difference.after is not None
    assert difference.after.definition_id == revised.id
    _ = await model.decide_review(case=correction, decision=choice, actor="reviewer")
    after = await model.compile(actor="reviewer")
    older = {item.proposal_id: item for item in before.content.source_alignments}
    newer = {item.proposal_id: item for item in after.content.source_alignments}
    assert older[unrelated.proposal_ids[0]] == newer[unrelated.proposal_ids[0]]
    assert newer[part.proposal_ids[0]].definition_id == revised.id
    assert after.content.definitions == before.content.definitions
    old_history = await model.get_review_history(case_id=part.id)
    assert old_history.items[0].id == mistaken.decision_id
    new_history = await model.get_review_history(case_id=correction.id)
    assert new_history.items[0].supersedes_decision_id == mistaken.decision_id
    with pytest.raises(StaleStateError, match="current effective"):
        _ = await model.reopen_review_case(
            actor="reviewer",
            case_id=part.id,
            expected_version=mistaken.case_version,
            proposal_ids=part.proposal_ids,
            reason="The occurrence already has a later decision.",
        )


async def test_plan_uses_the_reviewed_prospective_mapping_target(tmp_path: Path) -> None:
    project = await Client(
        config=ClientConfiguration(base_dir=tmp_path, model_gateway=_Gateway()),
    ).create_project(actor="editor", name="manufacturing")
    model = await project.create_model(
        actor="editor",
        name="planned-repair",
        kind=ModelKind.OBSERVED,
        description="Preserve separate meanings for catalog types and serialized items.",
    )
    capture = await _capture(project=project)
    draft = await model.extract_proposals(actor="editor", source_revisions=[capture.revision])
    alignment = await model.propose_alignment(actor="editor", discovery_id=draft.id)
    source = next(
        item
        for item in (await model.list_review_cases(reconciliation_id=alignment.id)).items
        if item.definitions[0].name == "part"
    )
    _ = await model.decide_review(
        actor="reviewer",
        case=source,
        decision=Accept(reason="Keep the interpreted source term."),
    )
    original = await model.get_review_case(case_id=source.id)
    before = await model.get_definition(name="part")
    repeat = await model.extract_proposals(actor="editor", source_revisions=[capture.revision])
    repeated_alignment = await model.propose_alignment(actor="editor", discovery_id=repeat.id)
    reused = next(
        item for item in repeated_alignment.suggestions if item.reused_decision_id is not None
    )
    assert reused.definition_id == before.id
    assert reused.evidence == source.evidence
    confirmation = await model.propose_confirmation(
        actor="reviewer",
        subject=original,
        reason="Review proof of the original interpretation.",
    )
    reopened = await project.get_model(name=model.info.name)
    builder = DomainModelBuilder(model_info=reopened.info)
    physical = builder.add_definition(
        name="serialized-unit",
        meaning="An individually tracked stock unit.",
        body=ConceptDefinition(),
    )
    builder.correct_mapping(
        case=original,
        decision=MapToPlannedDefinition(
            definition_id=physical,
            reason="Bind the original occurrence to the final new meaning.",
        ),
        proposal_ids=original.proposal_ids,
    )
    plan = builder.build_change_plan(reason="Review the definition and exact correction together.")
    parent = await model.propose_change_plan(
        plan=replace(plan, operations=plan.operations[::-1]),
        actor="editor",
    )
    approve = Accept(reason="Review the new meaning and repair together.")
    impact = await model.preview_changes(case=parent, decision=approve)
    (mapping,) = impact.source_alignment_changes
    assert mapping.before is not None
    assert mapping.before.definition_id == before.id
    assert mapping.after is not None
    assert mapping.after.definition_id == physical
    _ = await model.decide_review(case=parent, decision=approve, actor="reviewer")
    actual = await model.get_definition(definition_id=physical)
    corrected = await model.get_review_history(case_id=parent.generated_member_case_ids[0])
    action = corrected.items[0].action
    assert isinstance(action, MapToDefinition)
    assert action.definition == actual
    assert await model.get_definition(name="part") == before
    old_case = await model.get_review_case(case_id=confirmation.id)
    assert old_case.status is CaseStatus.SUPERSEDED
    current = await model.list_review_cases(kind=CaseKind.CONFIRMATION, status=CaseStatus.PENDING)
    (replacement,) = current.items
    assert replacement.confirmation_subject_id == parent.generated_member_case_ids[0]
    assert replacement.proposal_ids == original.proposal_ids
