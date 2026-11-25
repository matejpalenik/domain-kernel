"""Review reference-pack changes without conflicting reservations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DomainModelBuilder,
    InvalidDecisionError,
    ModelKind,
    Reject,
    StaleStateError,
)
from tests.support.reference_packs.write_catalog import write_catalog

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_pending_pack_changes_exclude_groups_and_a_stale_intent_can_be_rejected(
    tmp_path: Path,
) -> None:
    pack = write_catalog(root=tmp_path / "pack")
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor", name="recruitment"
    )
    model = await project.create_model(
        actor="editor",
        name="scope",
        kind=ModelKind.PROPOSED,
        description="Review scope changes.",
        reference_pack=pack,
    )
    removal = await model.propose_reference_pack_change(
        actor="editor",
        reference_pack=None,
        expected_workspace_revision=model.info.revision,
        reason="Inspect the removal.",
    )
    refreshed = await project.get_model(name=model.info.name)
    with pytest.raises(InvalidDecisionError, match="pending scope or grouped review"):
        _ = await refreshed.propose_reference_pack_change(
            actor="editor",
            reference_pack=None,
            expected_workspace_revision=refreshed.info.revision,
            reason="Try a second scope change.",
        )
    builder = DomainModelBuilder(model_info=refreshed.info)
    _ = builder.add_definition(
        name="system", meaning="An application system.", body=ConceptDefinition()
    )
    plan = builder.build_change_plan(reason="Review related terms as a group.")
    with pytest.raises(InvalidDecisionError, match="pending reference-pack change"):
        _ = await refreshed.propose_change_plan(actor="editor", plan=plan)
    unrelated = await refreshed.propose_definition(
        actor="editor",
        name="contact",
        meaning="A local contact.",
        body=ConceptDefinition(),
        reason="Review unrelated local work.",
    )
    accept = Accept(reason="Keep the inspected meaning.")
    _ = await refreshed.decide_review(case=unrelated, decision=accept, actor="reviewer")
    with pytest.raises(StaleStateError):
        _ = await refreshed.decide_review(case=removal, decision=accept, actor="reviewer")
    _ = await refreshed.decide_review(
        case=removal, decision=Reject(reason="Keep the currently selected pack."), actor="reviewer"
    )
    current = await project.get_model(name=model.info.name)
    assert current.info.reference_pack == pack.pin
    assert await current.get_concept(name="contact")
    next_builder = DomainModelBuilder(model_info=current.info)
    _ = next_builder.add_definition(
        name="system", meaning="An application system.", body=ConceptDefinition()
    )
    _ = await current.propose_change_plan(
        actor="editor", plan=next_builder.build_change_plan(reason="Now reserve the local group.")
    )
    current = await project.get_model(name=model.info.name)
    with pytest.raises(InvalidDecisionError, match="pending scope or grouped review"):
        _ = await current.propose_reference_pack_change(
            actor="editor",
            reference_pack=None,
            expected_workspace_revision=current.info.revision,
            reason="Wait for the coordinated local review.",
        )
