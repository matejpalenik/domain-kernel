"""Verify the structure and local identity of descriptive processes."""

import pytest

from domain_kernel import (
    Activity,
    ActivityId,
    Condition,
    Event,
    EventKind,
    Flow,
    FlowKind,
    Gateway,
    GatewayDirection,
    GatewayKind,
    ProcessDefinition,
    ProcessPartAlreadyExistsError,
    Role,
)


def test_process_keeps_explicit_nominal_children_and_detaches_lists() -> None:
    editor = Role(name="editor", meaning="Reviews the recruited system.")
    created = Event(name="created", kind=EventKind.START)
    review = Activity(name="review", roles=[editor])
    complete = Event(name="completed", kind=EventKind.END)
    activities = [review]
    body = ProcessDefinition(
        activities=activities,
        events=[created, complete],
        roles=[editor],
        flows=[
            Flow(name="start-review", source=created, target=review),
            Flow(name="end-review", source=review.id, target=complete.id),
        ],
    )
    activities.clear()
    assert body.activities == (review,)
    assert body.activities[0].role_ids == (editor.id,)
    assert body.flows[0].source_id == created.id
    assert type(body.flows[0].target_id) is ActivityId
    assert body.flows[1].target_id == complete.id


def test_process_rejects_duplicate_names_and_omitted_referenced_parts() -> None:
    editor = Role(name="reviewer", meaning="Inspects the submitted system.")
    start = Event(name="submitted", kind=EventKind.START)
    task = Activity(name="reviewer", roles=[editor])
    end = Event(name="decided", kind=EventKind.END)
    flows = [
        Flow(name="begin", source=start, target=task),
        Flow(name="finish", source=task, target=end),
    ]
    with pytest.raises(ProcessPartAlreadyExistsError):
        _ = ProcessDefinition(activities=[task], roles=[editor], events=[start, end], flows=flows)
    with pytest.raises(ValueError, match="role"):
        _ = ProcessDefinition(activities=[task], roles=[], events=[start, end], flows=flows)


def test_condition_input_symbols_remain_distinct_from_generated_ids() -> None:
    condition = Condition(
        name="significant-risk",
        description="Record the reviewer's assessment.",
        expression="significant_risk",
        input_ids=["significant_risk"],
    )
    assert condition.input_ids == ("significant_risk",)
    assert condition.id.value != condition.name


def test_exclusive_gateway_requires_one_default_and_local_endpoints() -> None:
    start = Event(name="begin", kind=EventKind.START)
    review = Activity(name="review")
    finish = Event(name="complete", kind=EventKind.END)
    split = Gateway(name="route", direction=GatewayDirection.SPLIT, kind=GatewayKind.EXCLUSIVE)
    condition = Condition(
        name="qualifies",
        description="Describe when the input qualifies.",
        expression="reviewed_input_qualifies",
    )
    flows = (
        Flow(name="begin-routing", source=start, target=split),
        Flow(
            name="review-qualified-input",
            source=split,
            target=review,
            kind=FlowKind.CONDITIONAL,
            condition=condition,
        ),
        Flow(
            name="complete-otherwise",
            source=split,
            target=finish,
            kind=FlowKind.CONDITIONAL,
            condition=condition,
        ),
        Flow(name="complete-review", source=review, target=finish),
    )
    with pytest.raises(ValueError, match="exactly one default"):
        _ = ProcessDefinition(
            activities=[review],
            events=[start, finish],
            roles=[],
            gateways=[split],
            flows=flows,
            conditions=[condition],
        )
    with pytest.raises(ValueError, match="flow endpoints"):
        _ = ProcessDefinition(
            activities=[],
            events=[start, finish],
            roles=[],
            gateways=[split],
            flows=flows,
            conditions=[condition],
        )


@pytest.mark.parametrize(
    ("can_enter_loop", "error"),
    [
        (False, "reachable from a start event"),
        (True, "have a path to an end event"),
    ],
)
def test_process_requires_both_a_path_from_start_and_a_path_to_end(
    *, can_enter_loop: bool, error: str
) -> None:
    start = Event(name="submitted", kind=EventKind.START)
    review = Activity(name="review")
    end = Event(name="done", kind=EventKind.END)
    follow_up = Activity(name="follow-up")
    flows = [
        Flow(name="begin", source=start, target=review),
        Flow(name="finish", source=review, target=end),
        Flow(name="repeat", source=follow_up, target=follow_up),
    ]
    if can_enter_loop:
        flows.append(Flow(name="request-follow-up", source=review, target=follow_up))

    with pytest.raises(ValueError, match=error):
        _ = ProcessDefinition(
            activities=[review, follow_up], events=[start, end], roles=[], flows=flows
        )
