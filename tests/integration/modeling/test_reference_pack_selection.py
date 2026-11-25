"""Preserve the exact working pack, obligations and published versions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    ApproveLocalExtension,
    CaseKind,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DefinitionAlreadyExistsError,
    DefinitionBinding,
    DomainModelBundle,
    InvalidDecisionError,
    MapToReference,
    ModelKind,
    PublicationBlockedError,
    ReferencePack,
    ReferencePackImport,
    ReferencePackSpec,
    Reject,
    StaleStateError,
)
from tests.support.reference_packs.write_catalog import write_catalog

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_workspace_retains_exact_selected_pack_after_reopening(tmp_path: Path) -> None:
    upstream = write_catalog(root=tmp_path / "packs", with_coverage=True)
    composed = ReferencePack.compose(
        spec=ReferencePackSpec(
            key="example.extension",
            version="1.0.0",
            title="Local extension",
            applicability="Reused local modeling vocabulary.",
            provenance="Authored example",
            license="Apache-2.0",
            imports=[
                ReferencePackImport(
                    reference_pack=upstream,
                    namespace="source",
                    pattern_ids=[upstream.get_pattern(name="system").id],
                    obligation_ids=[],
                )
            ],
        ),
        actor="author",
        reason="Omit upstream review obligations explicitly.",
    )
    assert composed.pack is not None
    pack = composed.pack
    config = ClientConfiguration(base_dir=tmp_path)
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author",
        name="with-pack",
        kind=ModelKind.PROPOSED,
        description="Use the selected reference pack.",
        reference_pack=pack,
    )
    assert model.info.reference_pack == pack.pin
    reopened_project = await Client(config=config).get_project(name=project.name)
    reopened = await reopened_project.get_model(name=model.info.name)
    assert reopened.info.reference_pack == pack.pin
    assert (await reopened_project.list_models()).items == (reopened.info,)
    pattern = pack.get_pattern(name="system")
    adopted = await reopened.propose_pattern(
        actor="author",
        pattern=pattern,
        reason="Inspect the reference system.",
        idempotency_key="reference-system-adoption",
    )
    assert not (await reopened.list_definitions()).items
    assert (
        await model.propose_pattern(
            actor="author",
            pattern=pattern,
            reason="Inspect the reference system.",
            idempotency_key="reference-system-adoption",
        )
    ).id == adopted.id
    plan = adopted.change_plan
    assert plan is not None
    assert plan.pattern_adoption is not None
    assert plan.pattern_adoption.reference_pack == pack.pin
    decision = Accept(reason="Approve the local adaptation.")
    _ = await model.decide_review(actor="reviewer", case=adopted, decision=decision)
    local = await model.get_concept(name="system")
    assert local.id.value != pattern.definitions[0].id.value
    before = await model.list_review_cases()
    with pytest.raises(DefinitionAlreadyExistsError):
        _ = await model.propose_pattern(actor="author", pattern=pattern, reason="Create it twice.")
    assert await model.list_review_cases() == before
    rebound = await model.propose_pattern(
        actor="author",
        pattern=pattern,
        bindings=[
            DefinitionBinding(
                reference_id=pattern.definitions[0].id,
                definition_id=local.id,
                definition_revision=local.revision,
            ),
        ],
        reason="Reuse the local identity explicitly.",
    )
    _ = await model.decide_review(actor="reviewer", case=rebound, decision=decision)
    assert await model.get_concept(name="system") == local
    prepared = await model.prepare_publication(actor="editor")
    assert any(item.code == "omitted_required_obligation" for item in prepared.validation.issues)
    bundle = await model.publish(
        publication=prepared,
        version="1.0.0",
        actor="owner",
        reason="Release the exact vocabulary with the recorded omission.",
    )
    assert DomainModelBundle.deserialize(payload=bundle.serialize()) == bundle


async def test_coverage_survives_release_and_extension_cannot_waive_it(tmp_path: Path) -> None:
    pack = write_catalog(root=tmp_path / "packs", with_coverage=True)
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        name="mapped",
        kind=ModelKind.PROPOSED,
        description="Review the scope against the selected pack.",
        reference_pack=pack,
    )
    case = await model.propose_pattern(
        actor="author",
        pattern=pack.get_pattern(name="system"),
        reason="Review the source shape.",
    )
    _ = await model.decide_review(
        actor="reviewer",
        case=case,
        decision=Accept(reason="Use the shape locally."),
    )
    local = await model.get_concept(name="system")
    extension_case = await model.propose_reference_alignment(
        actor="editor",
        local_definition=local,
        reason="Inspect the local shape.",
    )
    _ = await model.decide_review(
        actor="reviewer",
        case=extension_case,
        decision=ApproveLocalExtension(
            definition_id=local.id, reason="This is local application meaning."
        ),
    )
    with pytest.raises(PublicationBlockedError) as blocked:
        _ = await model.prepare_publication(actor="editor")
    assert "reference_coverage_missing" in {issue.code for issue in blocked.value.issues}

    mapping_case = await model.propose_reference_alignment(
        actor="editor",
        local_definition=local,
        reason="Review exact reference coverage.",
    )
    duplicate = await model.propose_reference_alignment(
        actor="editor",
        local_definition=local,
        reason="Request a separate inspection.",
    )
    reference = pack.definitions[0]
    mapping = mapping_case.same_as(
        local_definition=local,
        reference_definition=reference,
        reason="Reviewed equivalent meanings.",
    )
    impact = await model.preview_changes(case=mapping_case, decision=mapping)
    assert not impact.definition_changes
    assert impact.changes.reference_disposition_changes
    _ = await model.decide_review(actor="reviewer", case=mapping_case, decision=mapping)
    with pytest.raises(StaleStateError):
        _ = await model.preview_changes(case=duplicate, decision=mapping)
    _ = await model.decide_review(
        actor="reviewer",
        case=duplicate,
        decision=Reject(reason="The current mapping was reviewed."),
    )
    history = await model.get_review_history(case_id=mapping_case.id)
    recorded = history.items[0].action
    assert isinstance(recorded, MapToReference)
    assert recorded.reference_definition.reference_pack == pack.pin
    prepared = await model.prepare_publication(actor="editor")
    bundle = await model.publish(
        publication=prepared,
        version="1",
        actor="reviewer",
        reason="Release the reviewed mapping.",
    )
    restored = DomainModelBundle.deserialize(payload=bundle.serialize())
    assert restored.publication.reference_pack == pack
    assert restored.content.reference_dispositions == bundle.content.reference_dispositions


async def test_working_pack_changes_are_explicit_and_leave_publications_exact(  # noqa: PLR0915 - One exact publication through a full pack lifecycle.
    tmp_path: Path,
) -> None:
    first = write_catalog(root=tmp_path / "first")
    second = write_catalog(root=tmp_path / "second", version="1.1.0", with_coverage=True)
    client = Client(config=ClientConfiguration(base_dir=tmp_path))
    project = await client.create_project(actor="editor", name="recruitment")
    model = await project.create_model(
        actor="editor", name="scope", kind=ModelKind.PROPOSED, description="Review pack changes."
    )
    proposed = await model.propose_definition(
        actor="editor",
        name="system",
        meaning="A local application system.",
        body=ConceptDefinition(),
        reason="Review the company meaning.",
    )
    accept = Accept(reason="Review the inspected scope.")
    revise = await model.decide_review(case=proposed, decision=accept, actor="reviewer")
    attach = await model.propose_reference_pack_change(
        actor="editor",
        reference_pack=first,
        expected_workspace_revision=revise.workspace_revision,
        reason="Use the authored vocabulary.",
    )
    assert attach.kind is CaseKind.REFERENCE_PACK_CHANGE
    assert attach.reference_pack_change is not None
    assert attach.reference_pack_change.before is None
    assert attach.reference_pack_change.after == first
    _ = await model.decide_review(case=attach, decision=accept, actor="reviewer")
    local = await model.get_concept(name="system")
    mapping = await model.propose_reference_alignment(
        actor="editor", local_definition=local, reason="Inspect the first pack's meaning."
    )
    reviewed = mapping.same_as(
        local_definition=local,
        reference_definition=first.definitions[0],
        reason="Both meanings describe this application system.",
    )
    _ = await model.decide_review(case=mapping, decision=reviewed, actor="reviewer")
    preparation = await model.prepare_publication(actor="reviewer")
    published = await model.publish(
        publication=preparation, version="1.0.0", actor="reviewer", reason="Release the baseline."
    )
    current = await project.get_model(name=model.info.name)
    with pytest.raises(InvalidDecisionError):
        _ = await current.propose_reference_pack_change(
            actor="editor",
            reference_pack=first,
            expected_workspace_revision=current.info.revision,
            reason="Keep selecting the original pack.",
        )
    replace_pack = await current.propose_reference_pack_change(
        actor="editor",
        reference_pack=second,
        expected_workspace_revision=current.info.revision,
        reason="Inspect the new coverage requirement.",
        idempotency_key="second-release",
    )
    impact = await current.preview_changes(case=replace_pack, decision=accept)
    assert impact.changes.before_reference_pack == first.pin
    assert impact.changes.after_reference_pack == second.pin
    assert impact.reference_pack_change is not None
    assert impact.reference_pack_change.added_obligation_ids == (second.obligations[0].id,)
    assert "reference_coverage_missing" in {item.code for item in impact.blockers}
    assert len(impact.reference_disposition_changes) == 1
    _ = await current.decide_review(case=replace_pack, decision=accept, actor="reviewer")
    reopened = await project.get_model(name=model.info.name)
    assert reopened.info.reference_pack == second.pin
    assert await reopened.get_concept(name="system") == local
    assert await reopened.get_version(version=published.version) == published
    with pytest.raises(StaleStateError):
        _ = await reopened.publish(
            publication=preparation,
            version="1.0.1",
            actor="reviewer",
            reason="Reuse the preparation.",
        )
    (generated,) = (
        await reopened.list_review_cases(
            kind=CaseKind.REFERENCE_ALIGNMENT, status=CaseStatus.PENDING
        )
    ).items
    assert generated.generated_by_pack_change_id == replace_pack.id
    with pytest.raises(PublicationBlockedError):
        _ = await reopened.prepare_publication(actor="reviewer")
    removal = await reopened.propose_reference_pack_change(
        actor="editor",
        reference_pack=None,
        expected_workspace_revision=reopened.info.revision,
        reason="Return to local scope.",
    )
    removed = await reopened.decide_review(case=removal, decision=accept, actor="reviewer")
    without_pack = await project.get_model(name=model.info.name)
    assert without_pack.info.reference_pack is None
    assert await without_pack.get_concept(name="system") == local
    assert (await without_pack.get_review_case(case_id=removal.id)).status is CaseStatus.RESOLVED
    obsolete = await without_pack.get_review_case(case_id=generated.id)
    assert obsolete.status is CaseStatus.SUPERSEDED
    assert obsolete.version == generated.version + 1
    assert obsolete.superseded_by_decision_id == removed.decision_id
    assert await without_pack.get_version(version=published.version) == published
    reviewed_scope = await without_pack.prepare_publication(actor="reviewer")
    detached_scope = await without_pack.publish(
        publication=reviewed_scope,
        version="1.1.0",
        actor="reviewer",
        reason="Release the revised local scope.",
    )
    consumer = DomainModelBundle.deserialize(payload=detached_scope.serialize())
    removal_record = next(
        item for item in consumer.publication.candidate.decisions if item.id == removed.decision_id
    )
    assert removal_record.reference_pack_change == removal.reference_pack_change
    assert consumer.publication.reference_pack is None
    reattach = await without_pack.propose_reference_pack_change(
        actor="editor",
        reference_pack=first,
        expected_workspace_revision=without_pack.info.revision,
        reason="Revisit the exact original pack in the current context.",
    )
    _ = await without_pack.decide_review(case=reattach, decision=accept, actor="reviewer")
    assert not (await without_pack.compile(actor="reviewer")).content.reference_dispositions
    manual = await without_pack.propose_reference_alignment(
        actor="editor",
        local_definition=local,
        reason="Start a fresh review of the reattached pack.",
    )
    assert manual.reference_before is None
    assert (await without_pack.get_review_history(case_id=mapping.id)).items[0].action == reviewed
