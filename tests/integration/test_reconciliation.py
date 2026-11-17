"""Exercise the separate source and reference review queues against exact snapshots."""

from __future__ import annotations

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
    MappingRelation,
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
