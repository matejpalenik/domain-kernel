"""Regenerate child identity only when definitions acquire a new owner."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.business_decisions import BusinessDecisionDefinition
from domain_kernel._shared.domain.data_shapes import AttributeDefinition, KeyDefinition
from domain_kernel._shared.domain.definitions import ConceptDefinition, StructuredValueDefinition
from domain_kernel._shared.domain.process_parts import (
    Activity,
    Condition,
    Event,
    Flow,
    Gateway,
    Role,
)
from domain_kernel._shared.domain.processes import ProcessDefinition

if TYPE_CHECKING:
    from domain_kernel._shared.domain.definitions import DefinitionBody
    from domain_kernel._shared.domain.process_parts import ProcessNode, ProcessNodeId


def _new_attribute(*, field: AttributeDefinition) -> AttributeDefinition:
    return AttributeDefinition(
        name=field.name,
        display_name=field.display_name,
        value_type=field.value_type,
        required=field.required,
        collection=field.collection,
        min_items=field.min_items,
        max_items=field.max_items,
        nullability=field.nullability,
        constraints=field.constraints,
        terminology=field.terminology,
    )


def _new_condition(*, condition: Condition) -> Condition:
    return Condition(
        name=condition.name,
        display_name=condition.display_name,
        description=condition.description,
        expression=condition.expression,
        input_ids=condition.input_ids,
        evidence=condition.evidence,
    )


def _new_process(*, body: ProcessDefinition) -> ProcessDefinition:
    roles = {
        role.id: Role(
            name=role.name,
            display_name=role.display_name,
            meaning=role.meaning,
            evidence=role.evidence,
        )
        for role in body.roles
    }
    conditions = {item.id: _new_condition(condition=item) for item in body.conditions}
    activities = {
        item.id: Activity(
            name=item.name,
            display_name=item.display_name,
            roles=tuple(roles[identity] for identity in item.role_ids),
            inputs=item.input_ids,
            outputs=item.output_ids,
            decision=item.decision_id,
            evidence=item.evidence,
        )
        for item in body.activities
    }
    events = {
        item.id: Event(
            name=item.name,
            display_name=item.display_name,
            kind=item.kind,
            evidence=item.evidence,
        )
        for item in body.events
    }
    gateways = {
        item.id: Gateway(
            name=item.name,
            display_name=item.display_name,
            kind=item.kind,
            direction=item.direction,
        )
        for item in body.gateways
    }
    nodes: dict[ProcessNodeId, ProcessNode] = {**activities, **events, **gateways}
    return replace(
        body,
        roles=tuple(roles.values()),
        activities=tuple(activities.values()),
        events=tuple(events.values()),
        gateways=tuple(gateways.values()),
        conditions=tuple(conditions.values()),
        flows=tuple(
            Flow(
                name=item.name,
                display_name=item.display_name,
                kind=item.kind,
                source=nodes[item.source_id],
                target=nodes[item.target_id],
                evidence=item.evidence,
                condition=None if item.condition_id is None else conditions[item.condition_id],
            )
            for item in body.flows
        ),
    )


def _new_decision(*, body: BusinessDecisionDefinition) -> BusinessDecisionDefinition:
    conditions = {item.id: _new_condition(condition=item) for item in body.conditions}
    return replace(
        body,
        conditions=tuple(conditions.values()),
        rules=tuple(
            replace(
                item,
                condition_ids=tuple(conditions[identity].id for identity in item.condition_ids),
            )
            for item in body.rules
        ),
    )


def _new_fields(*, body: ConceptDefinition | StructuredValueDefinition) -> DefinitionBody:
    fields = {item.id: _new_attribute(field=item) for item in body.attributes}
    attributes = tuple(fields.values())
    if isinstance(body, ConceptDefinition):
        keys = tuple(
            KeyDefinition(
                name=key.name,
                display_name=key.display_name,
                attributes=tuple(fields[identity].id for identity in key.attributes),
            )
            for key in body.keys
        )
        return replace(body, attributes=attributes, keys=keys)
    quantity = body.quantity
    if quantity is not None:
        quantity = replace(
            quantity,
            magnitude=fields[quantity.magnitude].id,
            unit=fields[quantity.unit].id,
        )
    return replace(body, attributes=attributes, quantity=quantity)


def copy_local_parts(*, body: DefinitionBody) -> DefinitionBody:
    """Remint owner-local parts and preserve all edges to the newly created identities."""
    if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
        return _new_fields(body=body)
    if isinstance(body, ProcessDefinition):
        return _new_process(body=body)
    if isinstance(body, BusinessDecisionDefinition):
        return _new_decision(body=body)
    return body
