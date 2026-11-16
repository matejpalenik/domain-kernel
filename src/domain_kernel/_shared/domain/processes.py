"""Validate authored process topology without running any business steps."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel._shared.domain.process_parts import (
    Activity,
    Condition,
    Event,
    EventKind,
    Flow,
    FlowKind,
    Gateway,
    GatewayDirection,
    GatewayKind,
    Role,
)
from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.errors import ProcessPartAlreadyExistsError
from domain_kernel.shared.validation import require_exact, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from domain_kernel._shared.domain.process_parts import (
        InspectedDefinition,
        ProcessNode,
        ProcessNodeId,
    )


@dataclass(frozen=True, kw_only=True)
class ProcessDefinition:
    """A complete descriptive process with explicitly owned parts."""

    activities: Sequence[Activity]
    events: Sequence[Event]
    roles: Sequence[Role]
    flows: Sequence[Flow]
    gateways: Sequence[Gateway] = ()
    conditions: Sequence[Condition] = ()
    kind: Literal[DefinitionKind.PROCESS] = DefinitionKind.PROCESS

    def __post_init__(self) -> None:
        """Freeze local parts and verify the graph and all local references."""
        require_exact(value=self.kind, expected=DefinitionKind, field="Process kind")
        if self.kind is not DefinitionKind.PROCESS:
            raise ValueError("Use the PROCESS definition kind")
        for field, collection, part in (
            ("activities", self.activities, Activity),
            ("events", self.events, Event),
            ("roles", self.roles, Role),
            ("flows", self.flows, Flow),
            ("gateways", self.gateways, Gateway),
            ("conditions", self.conditions, Condition),
        ):
            object.__setattr__(
                self,
                field,
                snapshot_sequence(items=collection, item_type=part, field=field),
            )
        parts = (
            *self.activities,
            *self.events,
            *self.roles,
            *self.flows,
            *self.gateways,
            *self.conditions,
        )
        if len({part.name for part in parts}) != len(parts) or len(
            {part.id.value for part in parts}
        ) != len(parts):
            raise ProcessPartAlreadyExistsError
        nodes = {node.id: node for node in (*self.activities, *self.events, *self.gateways)}
        self._require_local_refs(nodes=nodes)
        _require_topology(nodes=nodes, flows=self.flows)

    def _require_local_refs(self, *, nodes: Mapping[ProcessNodeId, ProcessNode]) -> None:
        roles = {item.id: item for item in self.roles}
        conditions = {item.id: item for item in self.conditions}
        if any(
            not set(activity.role_ids) <= roles.keys()
            or any(roles.get(role.id) != role for role in activity.referenced_roles)
            for activity in self.activities
        ):
            raise ValueError("Supply the exact referenced activity role in this process")
        for flow in self.flows:
            if not {flow.source_id, flow.target_id} <= nodes.keys() or any(
                nodes.get(part.id) != part for part in flow.referenced_nodes
            ):
                raise ValueError("Supply the exact referenced flow endpoints in this process")
            if (flow.condition_id is not None and flow.condition_id not in conditions) or any(
                conditions.get(item.id) != item for item in flow.referenced_conditions
            ):
                raise ValueError("Supply the exact referenced flow condition in this process")

    @property
    def referenced_definitions(self) -> tuple[InspectedDefinition, ...]:
        """Expose supplied model snapshots for exact authored-plan bindings."""
        return tuple(
            definition
            for activity in self.activities
            for definition in activity.referenced_definitions
        )


def _walk(
    *,
    starting: Iterable[ProcessNodeId],
    connected: Mapping[ProcessNodeId, Sequence[Flow]],
    reverse: bool,
) -> set[ProcessNodeId]:
    pending = deque(starting)
    known: set[ProcessNodeId] = set()
    while pending:
        node = pending.popleft()
        if node in known:
            continue
        known.add(node)
        pending.extend(
            flow.source_id if reverse else flow.target_id for flow in connected.get(node, ())
        )
    return known


def _require_topology(
    *,
    nodes: Mapping[ProcessNodeId, ProcessNode],
    flows: Sequence[Flow],
) -> None:
    exits: defaultdict[ProcessNodeId, list[Flow]] = defaultdict(list)
    entries: defaultdict[ProcessNodeId, list[Flow]] = defaultdict(list)
    for flow in flows:
        exits[flow.source_id].append(flow)
        entries[flow.target_id].append(flow)
        _require_branch(flow=flow, source=nodes[flow.source_id], target=nodes[flow.target_id])
    starts = [
        node.id
        for node in nodes.values()
        if isinstance(node, Event) and node.kind is EventKind.START
    ]
    ends = [
        node.id for node in nodes.values() if isinstance(node, Event) and node.kind is EventKind.END
    ]
    if not starts or not ends:
        raise ValueError("Include a start and an end event")
    for node in nodes.values():
        incoming, outgoing = entries[node.id], exits[node.id]
        if isinstance(node, Event):
            _require_event(event=node, incoming=incoming, outgoing=outgoing)
        elif isinstance(node, Gateway):
            _require_gateway(gateway=node, incoming=incoming, outgoing=outgoing)
    if _walk(starting=starts, connected=exits, reverse=False) != set(nodes):
        raise ValueError("Every process node must be reachable from a start event")
    if _walk(starting=ends, connected=entries, reverse=True) != set(nodes):
        raise ValueError("Every process node must have a path to an end event")


def _require_branch(*, flow: Flow, source: ProcessNode, target: ProcessNode) -> None:
    if flow.kind in (FlowKind.CONDITIONAL, FlowKind.DEFAULT) and (
        not isinstance(source, Gateway)
        or source.direction is not GatewayDirection.SPLIT
        or source.kind is not GatewayKind.EXCLUSIVE
    ):
        raise ValueError("Conditional and default flows originate at an exclusive split")
    if (flow.kind is FlowKind.EXCEPTION) != (
        isinstance(target, Event) and target.kind is EventKind.EXCEPTION
    ):
        raise ValueError("Exception flows must lead to an explicit exception event")


def _require_event(*, event: Event, incoming: Sequence[Flow], outgoing: Sequence[Flow]) -> None:
    if event.kind is EventKind.START and (
        incoming or len(outgoing) != 1 or outgoing[0].kind is not FlowKind.NORMAL
    ):
        raise ValueError("A start event has no entry and one normal exit")
    if event.kind is EventKind.END and outgoing:
        raise ValueError("An end event has no outgoing flow")
    if event.kind is EventKind.EXCEPTION and not any(
        flow.kind is FlowKind.NORMAL for flow in outgoing
    ):
        raise ValueError("An exception event needs a normal recovery path")


def _require_gateway(
    *, gateway: Gateway, incoming: Sequence[Flow], outgoing: Sequence[Flow]
) -> None:
    branch_count_minimum = 2
    if gateway.direction is GatewayDirection.JOIN:
        if (
            len({flow.source_id for flow in incoming}) < branch_count_minimum
            or len(outgoing) != 1
            or outgoing[0].kind is not FlowKind.NORMAL
        ):
            raise ValueError("A join needs at least two inputs and one normal exit")
    elif len(incoming) != 1 or len({flow.target_id for flow in outgoing}) < branch_count_minimum:
        raise ValueError("A split needs one input and at least two exits")
    elif gateway.kind is GatewayKind.PARALLEL:
        if any(flow.kind is not FlowKind.NORMAL for flow in outgoing):
            raise ValueError("Parallel branches require normal flows")
    elif sum(flow.kind is FlowKind.DEFAULT for flow in outgoing) != 1 or any(
        flow.kind not in (FlowKind.CONDITIONAL, FlowKind.DEFAULT) for flow in outgoing
    ):
        raise ValueError("Exclusive splits need conditional branches and exactly one default")
