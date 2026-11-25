"""Capture, validate and reload a fixed candidate using the public SDK."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    AuditAction,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DomainModelBuilder,
    MeaningText,
    ModelKind,
    StaleStateError,
)
from domain_kernel._shared.domain.acceptance import (
    AcceptanceCheckDefinition,
    CheckOutcome,
    CheckRequirement,
    DistinctDefinitionsCheck,
    ManualCriterion,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_compiled_candidates_are_deterministic_and_exactly_reloaded(tmp_path: Path) -> None:
    config = ClientConfiguration(base_dir=tmp_path)
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing model.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    provider = builder.add_concept(name="provider", meaning="A business provider.")
    deployer = builder.add_concept(name="deployer", meaning="A business deployer.")
    _ = builder.add_definition(
        name="distinct-roles",
        meaning="Distinguish responsibilities.",
        body=AcceptanceCheckDefinition(
            statement=MeaningText(
                value="The provider and deployer have different definition identities."
            ),
            requirement=CheckRequirement.REQUIRED,
            predicate=DistinctDefinitionsCheck(left=provider, right=deployer),
        ),
    )
    _ = builder.add_definition(
        name="human-check",
        meaning="Inspect the allocation of duties.",
        body=AcceptanceCheckDefinition(
            statement=MeaningText(value="A reviewer confirms interpretation of the source."),
            requirement=CheckRequirement.ADVISORY,
            predicate=ManualCriterion(),
        ),
    )
    plan = builder.build_change_plan(reason="Review the initial concepts and checks.")
    case = await model.propose_change_plan(actor="author", plan=plan)
    _ = await model.decide_review(actor="reviewer", case=case, decision=Accept(reason=plan.reason))
    first = await model.compile(actor="editor")
    again = await model.compile(actor="editor")
    assert first.id != again.id
    assert first.content_hash == again.content_hash
    _ = await model.propose_definition(
        actor="author",
        name="pending",
        meaning="An unreviewed term.",
        body=ConceptDefinition(),
        reason="Inspect the term separately.",
    )
    changed = await model.compile(actor="editor")
    assert changed.content_hash != first.content_hash
    assert changed.content == first.content
    reopened_project = await Client(config=config).get_project(name=project.name)
    reopened = await reopened_project.get_model(name=model.info.name)
    stored = await reopened.get_candidate(candidate_id=first.id)
    assert stored == first
    report = await reopened.validate(actor="editor", candidate=stored)
    assert report.candidate_hash == first.content_hash
    assert not report.issues
    assert tuple(result.outcome for result in report.acceptance) == (
        CheckOutcome.PASS,
        CheckOutcome.UNKNOWN,
    )
    with pytest.raises(StaleStateError):
        _ = await reopened.validate(
            actor="editor", candidate=replace(stored, description="Modified.")
        )
    events = (await reopened.get_audit_history()).items
    assert events[-1].action is AuditAction.VALIDATE
