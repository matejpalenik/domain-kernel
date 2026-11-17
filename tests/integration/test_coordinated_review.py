"""Exercise coordinated reservations and decisions using independent workspace clients."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from domain_kernel import (
    Accept,
    CaseKind,
    CaseStatus,
    Client,
    ConceptDefinition,
    DefinitionAlreadyExistsError,
    IdempotencyConflictError,
    InvalidDecisionError,
    ModelKind,
    Reject,
    RelationshipCardinality,
    StaleStateError,
)
from domain_kernel.authoring import DomainModelBuilder
from domain_kernel.review.domain.models import CaseDecision

if TYPE_CHECKING:
    from domain_kernel.modeling.api.model import Model
    from tests.integration.conftest import DatabaseBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_connected_plan_is_reserved_once_and_reviewed_atomically(
    database_backend: DatabaseBackend,
) -> None:
    config = database_backend.config
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing model.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    applicant = builder.add_concept(display_name="Applicant", meaning="A person applying.")
    reviewer = builder.add_concept(
        display_name="Reviewer", meaning="An actor reviewing applications."
    )
    relation = builder.add_relationship(
        display_name="Reviews",
        meaning="The reviewer examines the applicant's application.",
        source=reviewer,
        target=applicant,
        cardinality=RelationshipCardinality.many_to_many(),
    )
    plan = builder.build_change_plan(reason="Represent the interaction in one change.")
    assert (await model.list_review_cases()).items == ()
    other_project = await Client(config=config).get_project(name=project.name)
    other_model = await other_project.get_model(name=model.info.name)
    original, duplicate = await asyncio.gather(
        model.propose_change_plan(actor="author", plan=plan),
        other_model.propose_change_plan(actor="author", plan=plan),
    )
    assert original == duplicate
    assert original.kind is CaseKind.CHANGE_SET
    assert len(original.generated_member_case_ids) == len(plan.operations)
    assert (await model.list_definitions()).items == ()

    with pytest.raises(IdempotencyConflictError):
        _ = await model.propose_change_plan(
            actor="another", plan=plan, idempotency_key="second-key"
        )
    first_member = await model.get_review_case(case_id=original.generated_member_case_ids[0])
    approval = Accept(reason="The combined graph preserves both endpoints.")
    with pytest.raises(InvalidDecisionError, match="parent"):
        _ = await model.decide_review(actor="reviewer", case=first_member, decision=approval)
    impact = await model.preview_changes(case=original, decision=approval)
    assert len(impact.definition_changes) == len(plan.operations)
    assert not impact.blockers
    receipt = await model.decide_review(actor="reviewer", case=original, decision=approval)
    assert len(receipt.member_decision_ids) == len(plan.operations)
    loaded = await other_model.get_relationship(relationship_id=relation)
    assert loaded.body.source_concept_id == reviewer
    assert loaded.body.target_concept_id == applicant


async def test_mixed_rejection_releases_existing_case_and_preserves_exact_history(
    database_backend: DatabaseBackend,
) -> None:
    project = await Client(config=database_backend.config).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing model.",
    )
    pending = await model.propose_definition(
        actor="author",
        name="reviewer",
        meaning="An actor reviewing candidates.",
        body=ConceptDefinition(),
        reason="Consider the reviewer role.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(display_name="Applicant", meaning="A person applying.")
    approval = Accept(reason="The role is in scope.")
    builder.include_case(case=pending, decision=approval)
    plan = builder.build_change_plan(reason="Review the actors jointly.")
    submitted = await model.propose_change_plan(actor="author", plan=plan)
    with pytest.raises(StaleStateError):
        _ = await model.propose_change_set(
            actor="author",
            decisions=[
                CaseDecision(
                    case_id=pending.id, expected_version=pending.version, decision=approval
                )
            ],
            expected_workspace_revision=model.info.revision,
            reason="Group old version.",
        )
    _ = await model.decide_review(
        actor="reviewer",
        case=submitted,
        decision=Reject(reason="Review the actors separately."),
    )
    replay = await model.propose_change_plan(actor="author", plan=plan)
    assert replay.status is CaseStatus.RESOLVED
    assert replay.id == submitted.id
    assert (await model.get_review_history(case_id=pending.id)).items == ()
    released = await model.get_review_case(case_id=pending.id)
    assert released.status is CaseStatus.PENDING
    assert released.grouped_by_case_id is None
    parent_history = (await model.get_review_history(case_id=submitted.id)).items[0]
    assert parent_history.released_case_ids == (pending.id,)
    assert parent_history.change_plan == plan
    new_case = await model.propose_definition(
        actor="author",
        name="applicant",
        meaning="A person applying to a specific role.",
        body=ConceptDefinition(),
        reason="Create a fresh proposal.",
    )
    rejected_case = await model.get_review_case(case_id=submitted.generated_member_case_ids[0])
    assert rejected_case.status is CaseStatus.RESOLVED
    assert rejected_case.definitions[0].id != new_case.definitions[0].id


async def test_partial_reservation_failure_has_no_orphan_members(
    database_backend: DatabaseBackend,
) -> None:
    project = await Client(config=database_backend.config).create_project(
        actor="author",
        name="recruitment",
    )
    model = await project.create_model(
        actor="author",
        name="observed",
        kind=ModelKind.OBSERVED,
        description="Existing model.",
    )
    pending = await model.propose_definition(
        actor="author",
        name="reserved",
        meaning="Meaning under separate inspection.",
        body=ConceptDefinition(),
        reason="Reserve the existing name.",
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(name="first", meaning="This reservation must roll back.")
    _ = builder.add_concept(name="reserved", meaning="This name already has a pending owner.")
    plan = builder.build_change_plan(reason="Try the proposed joined vocabulary.")

    with pytest.raises(DefinitionAlreadyExistsError):
        _ = await model.propose_change_plan(actor="author", plan=plan)
    assert (await model.list_review_cases()).items == (pending,)
    assert (await model.list_definitions()).items == ()
    _ = await model.propose_definition(
        actor="author",
        name="first",
        meaning="A fresh independent definition.",
        body=ConceptDefinition(),
        reason="Verify the name is free.",
    )


async def test_competing_decisions_commit_once_across_clients(
    database_backend: DatabaseBackend,
) -> None:
    config = database_backend.config
    project = await Client(config=config).create_project(actor="author", name="recruitment")
    model = await project.create_model(
        actor="author", name="review", kind=ModelKind.PROPOSED, description="Review the plan."
    )
    builder = DomainModelBuilder(model_info=model.info)
    _ = builder.add_concept(name="reviewer", meaning="A person screening applications.")
    case = await model.propose_change_plan(
        actor="author", plan=builder.build_change_plan(reason="Define the reviewer role.")
    )
    reopened = await Client(config=config).get_project(name=project.name)
    competitor = await reopened.get_model(name=model.info.name)

    async def decide(*, selected: Model, actor: str, outcome: Accept | Reject) -> bool:
        try:
            _ = await selected.decide_review(actor=actor, case=case, decision=outcome)
        except StaleStateError:
            return False
        return True

    results = await asyncio.gather(
        decide(selected=model, actor="reviewer-a", outcome=Accept(reason="The role is in scope.")),
        decide(
            selected=competitor, actor="reviewer-b", outcome=Reject(reason="The role is unclear.")
        ),
    )
    assert sorted(results) == [False, True]
    history = await competitor.get_review_history(case_id=case.id)
    assert len(history.items) == 1
