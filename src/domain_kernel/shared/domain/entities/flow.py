"""Describe an edge between nodes in a process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Never, override
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.flow_id import FlowId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.entities.condition import Condition
from domain_kernel.shared.domain.entities.event import Event
from domain_kernel.shared.domain.entities.gateway import Gateway
from domain_kernel.shared.domain.entities.part_snapshot import PartSnapshot
from domain_kernel.shared.domain.enums.flow_kind import FlowKind
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.domain.types.process_node import ProcessNode
    from domain_kernel.shared.domain.types.process_node_id import ProcessNodeId


@dataclass(frozen=True, kw_only=True, init=False)
class Flow(PartSnapshot):
    """An identified typed connection between explicitly authored process nodes."""

    id: FlowId
    name: str
    display_name: str
    source_id: ProcessNodeId
    target_id: ProcessNodeId
    kind: FlowKind
    condition_id: ConditionId | None
    evidence: tuple[()]
    _nodes: ClassVar[tuple[ProcessNode, ...]] = ()
    _conditions: ClassVar[tuple[Condition, ...]] = ()

    def __init__(  # noqa: PLR0913 - Exact endpoints and optional branch data.
        self,
        *,
        source: ProcessNode | ProcessNodeId,
        target: ProcessNode | ProcessNodeId,
        display_name: str | None = None,
        name: str | None = None,
        kind: FlowKind = FlowKind.NORMAL,
        condition: Condition | ConditionId | None = None,
        evidence: Sequence[Never] = (),
    ) -> None:
        """Capture an exact typed edge and its optional inert condition."""
        lookup, label = LookupNamingPolicy.resolve_names(name=name, display_name=display_name)

        self._set_fields(
            attributes={
                "id": FlowId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "kind": kind,
                "source_id": source.id
                if isinstance(source, (Activity, Event, Gateway))
                else source,
                "target_id": target.id
                if isinstance(target, (Activity, Event, Gateway))
                else target,
                "condition_id": condition.id if isinstance(condition, Condition) else condition,
                "evidence": self._snapshot_evidence(evidence=evidence),
                "_nodes": tuple(
                    node
                    for node in (source, target)
                    if isinstance(node, (Activity, Event, Gateway))
                ),
                "_conditions": (condition,) if isinstance(condition, Condition) else (),
            },
        )

        self._validate()

    @override
    def _validate(self) -> None:
        """Check the flow's endpoints, kind and optional condition identity."""
        RuntimeTypeValidation.require_exact(value=self.id, expected=FlowId, field="Flow ID")
        self._require_names(name=self.name, display_name=self.display_name)

        RuntimeTypeValidation.require_exact(value=self.kind, expected=FlowKind, field="Flow kind")

        if any(
            type(item) not in (ActivityId, EventId, GatewayId)
            for item in (self.source_id, self.target_id)
        ):
            raise TypeError("Use exact typed process node IDs")

        if self.condition_id is not None:
            RuntimeTypeValidation.require_exact(
                value=self.condition_id, expected=ConditionId, field="Condition ID"
            )
        if (self.condition_id is not None) != (self.kind is FlowKind.CONDITIONAL):
            raise ValueError("Only a conditional flow requires an explicit condition")

        _ = self._snapshot_evidence(evidence=self.evidence)

    @property
    def referenced_nodes(self) -> tuple[ProcessNode, ...]:
        """Supplied node snapshots for exact local verification."""
        return self._nodes

    @property
    def referenced_conditions(self) -> tuple[Condition, ...]:
        """Supplied condition snapshots for exact local verification."""
        return self._conditions
