"""Test case-local review before persistence and service composition."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain_kernel import (
    AttributeDefinition,
    BusinessCode,
    CaseKind,
    CaseStatus,
    CollectionKind,
    ConceptDefinition,
    Count,
    DecimalFacets,
    DecimalPrecision,
    DecimalScale,
    Definition,
    DefinitionId,
    DefinitionStatus,
    InvalidDecisionError,
    LabelText,
    MeaningText,
    ModelId,
    ModelScope,
    ProjectId,
    ProposalId,
    ReviewCaseId,
    StaleStateError,
    ValueSetDefinition,
    ValueSetMember,
    ValueSetMembership,
)
from domain_kernel._shared.domain.changes import (
    ChangeSet,
    ComparisonKind,
    Compatibility,
    SourceAlignment,
    SourceAlignmentChange,
    SourceDisposition,
)
from domain_kernel._shared.domain.record_encoding import read_record, record_bytes
from domain_kernel.review.domain.coordinated import member_effects
from domain_kernel.review.domain.decisions import Accept, EditDefinition, Reject
from domain_kernel.review.domain.models import (
    CaseDecision,
    ReviewCase,
    ReviewImpact,
    preview_case,
    resolve_case,
)


@pytest.fixture
def proposal() -> ReviewCase:
    scope = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model"))
    definition = Definition(
        id=DefinitionId(value="machine"),
        scope=scope,
        revision=1,
        name="machine",
        display_name="Machine",
        meaning="Physical production asset.",
        body=ConceptDefinition(),
    )
    return ReviewCase(
        id=ReviewCaseId(value="review"),
        scope=scope,
        version=1,
        status=CaseStatus.PENDING,
        kind=CaseKind.PROPOSAL,
        definitions=[definition],
        reason="Owner-authored meaning.",
    )


def test_accept_resolves_only_the_inspected_proposal(proposal: ReviewCase) -> None:
    accept = Accept(reason="The meaning matches the catalog.")
    changes = preview_case(case=proposal, decision=accept)
    assert tuple(value.status for value in changes) == (DefinitionStatus.APPROVED,)
    assert changes[0].meaning == "Physical production asset."
    resolved = resolve_case(
        case=proposal,
        decision=accept,
        actor="reviewer",
        expected_version=1,
        now=datetime.now(tz=UTC),
    )
    assert resolved.status is CaseStatus.RESOLVED
    assert resolved.version == proposal.version + 1
    assert proposal.status is CaseStatus.PENDING
    assert proposal.definitions[0].status is DefinitionStatus.PROPOSED


def test_reject_has_no_effect_and_a_stale_decision_cannot_advance(proposal: ReviewCase) -> None:
    reject = Reject(reason="The definition is out of scope.")
    assert not preview_case(case=proposal, decision=reject)
    with pytest.raises(StaleStateError):
        _ = resolve_case(
            case=proposal,
            decision=reject,
            actor="reviewer",
            expected_version=2,
            now=datetime.now(tz=UTC),
        )
    assert proposal.version == 1


def test_edit_retains_identity_and_fails_for_different_target(proposal: ReviewCase) -> None:
    edit = EditDefinition(
        definition_id=proposal.definitions[0].id,
        name="machine",
        display_name="Machine",
        body=ConceptDefinition(),
        reason="Clarify the inspected proposal.",
        meaning="An individually maintained production asset.",
    )
    changes = preview_case(case=proposal, decision=edit)
    assert changes[0].id == proposal.definitions[0].id
    assert changes[0].meaning == edit.meaning
    wrong = EditDefinition(
        definition_id=DefinitionId(value="other"),
        name=edit.name,
        display_name=edit.display_name,
        body=edit.body,
        reason=edit.reason,
        meaning=edit.meaning,
    )
    with pytest.raises(InvalidDecisionError):
        _ = preview_case(case=proposal, decision=wrong)


def test_mapping_only_impact_is_a_view_of_the_same_changes(proposal: ReviewCase) -> None:
    alignment = SourceAlignment(
        proposal_id=ProposalId(value="occurrence"),
        definition_id=DefinitionId(value="machine"),
        definition_revision=1,
        disposition=SourceDisposition.MAPPED,
        decision_id=None,
        rationale="The occurrence uses the same meaning.",
        context_fingerprint="inspected-context",
    )
    changes = ChangeSet(
        scope=proposal.scope,
        changes=(),
        compatibility=Compatibility.COMPATIBLE,
        comparison=ComparisonKind.PROPOSAL,
        source_alignment_changes=[SourceAlignmentChange(before=None, after=alignment)],
    )
    impact = ReviewImpact(changes=changes, workspace_revision=1, affected_case_ids=(proposal.id,))
    wire = record_bytes(value=changes)

    assert impact.definition_changes == ()
    assert impact.source_alignment_changes is changes.source_alignment_changes
    assert impact.reference_disposition_changes is changes.reference_disposition_changes
    assert record_bytes(value=impact.changes) == wire
    assert read_record(content=wire, expected=ChangeSet) == changes


def test_definition_record_round_trips_bounds_decimal_and_nominal_unit_links(
    proposal: ReviewCase,
) -> None:
    amount = AttributeDefinition.decimal(
        name="amount",
        required=False,
        collection=CollectionKind.LIST,
        max_items=Count(value=4),
        facets=DecimalFacets(precision=DecimalPrecision(value=5), scale=DecimalScale(value=2)),
    )
    concept = replace(proposal.definitions[0], body=ConceptDefinition(attributes=[amount]))
    units = replace(
        proposal.definitions[0],
        body=ValueSetDefinition(
            membership=ValueSetMembership.CLOSED,
            members=[
                ValueSetMember(
                    code=BusinessCode(value="h"),
                    label=LabelText(value="Hour"),
                    meaning=MeaningText(value="An hour of elapsed time."),
                    unit=DefinitionId(value="hour"),
                )
            ],
        ),
    )

    for record in (concept, units):
        wire = record_bytes(value=record)
        assert read_record(content=wire, expected=Definition) == record
        with pytest.raises(ValueError, match="canonical"):
            _ = read_record(content=wire + b" ", expected=Definition)


def test_group_rejection_resolves_generated_members_and_releases_included_ones(
    proposal: ReviewCase,
) -> None:
    parent_id = ReviewCaseId(value="group")
    generated = replace(proposal, grouped_by_case_id=parent_id)
    included = replace(proposal, id=ReviewCaseId(value="included"), grouped_by_case_id=parent_id)
    pending = Accept(reason="Reviewed meaning.")
    parent = replace(
        proposal,
        id=parent_id,
        kind=CaseKind.CHANGE_SET,
        definitions=(),
        members=[
            CaseDecision(
                case_id=generated.id, expected_version=generated.version, decision=pending
            ),
            CaseDecision(case_id=included.id, expected_version=included.version, decision=pending),
        ],
        generated_member_case_ids=[generated.id],
        guarded_workspace_revision=1,
    )
    reject = Reject(reason="Reconsider the graph.")
    effects = member_effects(
        parent=parent,
        members=[generated, included],
        decision=reject,
    )

    assert effects[0].after.status is CaseStatus.RESOLVED
    assert effects[0].action == reject
    assert effects[1].after.status is CaseStatus.PENDING
    assert effects[1].action is None
    assert all(effect.after.grouped_by_case_id is None for effect in effects)
    assert all(effect.definitions == () for effect in effects)
    assert included.grouped_by_case_id == parent_id
    with pytest.raises(StaleStateError):
        _ = member_effects(
            parent=parent,
            members=[replace(generated, version=2), included],
            decision=reject,
        )
