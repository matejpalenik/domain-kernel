"""Assert the public continuation guards against persisted source runs."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    Client,
    ClientConfiguration,
    LangGraphDiscoveryGateway,
    RunStatus,
    StaleStateError,
)
from tests.support.discovery.create_discovery_workspace import create_discovery_workspace
from tests.support.discovery.v23_gateway import V23Gateway

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("change_profile", "reason"),
    [(False, "deferred omission"), (True, "original discovery workflow")],
    ids=["no-deferred-work", "different-profile"],
)
async def test_rejected_continuation_does_not_open_a_child_or_change_history(
    tmp_path: Path, *, change_profile: bool, reason: str
) -> None:
    provider = V23Gateway()
    gateway = LangGraphDiscoveryGateway(
        gateway=provider,
        profile="fixture/parent",
        directory=tmp_path / "receipts",
        proposal_batching=True,
        resumable_omissions=True,
    )
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=gateway)
    parent = await model.discover(actor="editor", sources=[revision])
    assert parent.status is RunStatus.NEEDS_REVIEW
    (case,) = (await model.list_review_cases(run_id=parent.id)).items
    _ = await model.decide_review(
        actor="reviewer", case=case, decision=Accept(reason="The source defines the lookup code.")
    )
    before = (await model.get_review_history(case_id=case.id)).items
    assert len(before) == 1
    audit = await model.get_audit_history()
    requests = tuple(provider.requests)

    config = ClientConfiguration(
        base_dir=tmp_path,
        model_gateway=replace(gateway, profile="fixture/different") if change_profile else gateway,
    )
    reopened = await Client(config=config).get_project(name="recruitment")
    current = await reopened.get_model(name="locators")
    with pytest.raises(StaleStateError, match=reason):
        _ = await current.continue_discovery(actor="editor", run_id=parent.id)

    assert (await current.list_discovery_runs()).items == (parent,)
    assert (await current.get_review_history(case_id=case.id)).items == before
    assert await current.get_audit_history() == audit
    assert tuple(provider.requests) == requests
