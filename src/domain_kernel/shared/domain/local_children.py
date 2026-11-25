"""Rewrite owner-local part identities and keep their internal references closed."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from itertools import count
from typing import TYPE_CHECKING
from uuid import uuid4

from domain_kernel.shared.domain.definitions import ConceptDefinition, StructuredValueDefinition
from domain_kernel.shared.domain.record_restoration import construct_record
from domain_kernel.shared.domain.semantic_definitions import (
    ModelTermReference,
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.shape_graph import remap_shape
from domain_kernel.shared.domain.value_objects.business_decision_definition import (
    BusinessDecisionDefinition,
)
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from domain_kernel.shared.contracts import DefinitionReference
    from domain_kernel.shared.domain.definitions import DefinitionBody
    from domain_kernel.shared.domain.semantic_definitions import SemanticTerm
    from domain_kernel.shared.domain.types.process_node_id import ProcessNodeId


def _part[T](*, value: T, next_id: Callable[[], str], **edges: object) -> T:
    if not is_dataclass(value):
        raise TypeError("Use a declared local part record")
    attributes: dict[str, object] = {
        field.name: getattr(value, field.name) for field in fields(value)
    }
    identifier = attributes.get("id")
    if not isinstance(identifier, OpaqueIdentifier):
        raise TypeError("Use a nominal local part identity")
    attributes.update(edges)
    attributes["id"] = type(identifier)(value=next_id())
    record = type(value)
    copied = construct_record(record=record, attributes=attributes)
    if not isinstance(copied, record):
        raise TypeError("Restore the declared local part record")
    return copied


def _process(*, body: ProcessDefinition, next_id: Callable[[], str]) -> ProcessDefinition:
    roles = {item.id: _part(value=item, next_id=next_id) for item in body.roles}
    conditions = {item.id: _part(value=item, next_id=next_id) for item in body.conditions}
    activities = {
        item.id: _part(
            value=item,
            next_id=next_id,
            role_ids=tuple(roles[identity].id for identity in item.role_ids),
        )
        for item in body.activities
    }
    events = {item.id: _part(value=item, next_id=next_id) for item in body.events}
    gateways = {item.id: _part(value=item, next_id=next_id) for item in body.gateways}
    nodes: dict[ProcessNodeId, ProcessNodeId] = {
        **{before: after.id for before, after in activities.items()},
        **{before: after.id for before, after in events.items()},
        **{before: after.id for before, after in gateways.items()},
    }
    return replace(
        body,
        roles=tuple(roles.values()),
        activities=tuple(activities.values()),
        events=tuple(events.values()),
        gateways=tuple(gateways.values()),
        conditions=tuple(conditions.values()),
        flows=tuple(
            _part(
                value=item,
                next_id=next_id,
                source_id=nodes[item.source_id],
                target_id=nodes[item.target_id],
                condition_id=None
                if item.condition_id is None
                else conditions[item.condition_id].id,
            )
            for item in body.flows
        ),
    )


def _decision(
    *,
    body: BusinessDecisionDefinition,
    next_id: Callable[[], str],
) -> BusinessDecisionDefinition:
    conditions = {item.id: _part(value=item, next_id=next_id) for item in body.conditions}
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


def _fields(
    *,
    body: ConceptDefinition | StructuredValueDefinition,
    next_id: Callable[[], str],
) -> DefinitionBody:
    attributes = {item.id: _part(value=item, next_id=next_id) for item in body.attributes}
    copied = tuple(attributes.values())
    if isinstance(body, ConceptDefinition):
        return replace(
            body,
            attributes=copied,
            keys=tuple(
                _part(
                    value=item,
                    next_id=next_id,
                    attributes=tuple(attributes[identity].id for identity in item.attributes),
                )
                for item in body.keys
            ),
        )
    quantity = body.quantity
    if quantity is not None:
        quantity = replace(
            quantity,
            magnitude=attributes[quantity.magnitude].id,
            unit=attributes[quantity.unit].id,
        )
    return replace(body, attributes=copied, quantity=quantity)


def _with_parts(*, body: DefinitionBody, next_id: Callable[[], str]) -> DefinitionBody:
    if isinstance(body, (ConceptDefinition, StructuredValueDefinition)):
        return _fields(body=body, next_id=next_id)
    if isinstance(body, ProcessDefinition):
        return _process(body=body, next_id=next_id)
    if isinstance(body, BusinessDecisionDefinition):
        return _decision(body=body, next_id=next_id)
    return body


def copy_local_parts(*, body: DefinitionBody) -> DefinitionBody:
    """Remint owner-local parts and keep all local references to those parts."""
    return _with_parts(body=body, next_id=lambda: uuid4().hex)


def normalize_local_parts(*, body: DefinitionBody) -> DefinitionBody:
    """Compare deterministic structure after removing newly minted child identities."""
    positions = count()
    return _with_parts(body=body, next_id=lambda: f"part-{next(positions)}")


def copy_shape_bodies[RefT: DefinitionReference](
    *,
    bodies: Mapping[RefT, DefinitionBody],
    replacements: Mapping[DefinitionReference, DefinitionReference],
    existing: Mapping[RefT, DefinitionBody] | None = None,
) -> dict[RefT, DefinitionBody]:
    """Remint local parts and rewrite all links to the copied owner-qualified fields."""
    supplied: Mapping[RefT, DefinitionBody] = {} if existing is None else existing
    captured = {
        key: copy_local_parts(body=body) for key, body in bodies.items() if key not in supplied
    }
    return _rewrite_shape_bodies(
        original=bodies,
        rewritten={**supplied, **captured},
        captured=captured,
        replacements=replacements,
    )


def comparable_shape_bodies[RefT: DefinitionReference](
    *,
    bodies: Mapping[RefT, DefinitionBody],
    replacements: Mapping[DefinitionReference, DefinitionReference],
) -> dict[RefT, DefinitionBody]:
    """Normalize linked local parts while comparing two exact model scopes."""
    normalized = {key: normalize_local_parts(body=body) for key, body in bodies.items()}
    return _rewrite_shape_bodies(
        original=bodies,
        rewritten=normalized,
        captured=normalized,
        replacements=replacements,
    )


def _rewrite_shape_bodies[RefT: DefinitionReference](
    *,
    original: Mapping[RefT, DefinitionBody],
    rewritten: Mapping[RefT, DefinitionBody],
    captured: Mapping[RefT, DefinitionBody],
    replacements: Mapping[DefinitionReference, DefinitionReference],
) -> dict[RefT, DefinitionBody]:
    attributes: dict[tuple[DefinitionReference, str], str] = {}
    for key, before in original.items():
        after = rewritten[key]
        if isinstance(before, (ConceptDefinition, StructuredValueDefinition)) and isinstance(
            after, (ConceptDefinition, StructuredValueDefinition)
        ):
            by_name = {field.name: field.id.value for field in after.attributes}
            for field in before.attributes:
                if field.name in by_name:
                    attributes[(key, field.id.value)] = by_name[field.name]

    def endpoint(*, term: SemanticTerm) -> SemanticTerm:
        if not isinstance(term, ModelTermReference) or not term.local_path:
            return term
        field = term.local_path[1]
        replacement = attributes.get((term.definition, field), field)
        return replace(term, local_path=("attributes", replacement))

    return {
        key: remap_shape(
            body=replace(
                body, subject=endpoint(term=body.subject), object=endpoint(term=body.object)
            )
            if isinstance(body, SemanticLinkDefinition)
            else body,
            replacements=replacements,
        )
        for key, body in captured.items()
    }
