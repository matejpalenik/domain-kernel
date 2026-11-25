"""Inspect the exact local parts of a descriptive process revision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.flow_id import FlowId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.shared.domain.definitions import Definition, require_definition_selector
from domain_kernel.shared.domain.records.activity import Activity
from domain_kernel.shared.domain.records.condition import Condition
from domain_kernel.shared.domain.records.event import Event
from domain_kernel.shared.domain.records.flow import Flow
from domain_kernel.shared.domain.records.gateway import Gateway
from domain_kernel.shared.domain.records.process_definition import ProcessDefinition
from domain_kernel.shared.domain.records.role import Role
from domain_kernel.shared.errors import ProcessPartNotFoundError
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


type _Part = Activity | Event | Flow | Gateway | Role | Condition


def _find_part[T: _Part](
    *,
    parts: Sequence[T],
    name: str | None,
    part_id: OpaqueIdentifier | None,
    identity_type: type[OpaqueIdentifier],
) -> T:
    require_definition_selector(name=name, item_id=part_id, id_type=identity_type)
    for part in parts:
        if part.name == name or part.id == part_id:
            return part
    raise ProcessPartNotFoundError


@dataclass(frozen=True, kw_only=True)
class Process(Definition[ProcessDefinition]):
    """An inspected process revision with immutable, owner-local child lookups."""

    @override
    def __post_init__(self) -> None:
        """Check that the inspected body is the exact process definition."""
        super().__post_init__()
        RuntimeTypeValidation.require_exact(
            value=self.body, expected=ProcessDefinition, field="Process body"
        )

    @property
    def activities(self) -> tuple[Activity, ...]:
        """Return the activities captured on this revision."""
        return tuple(self.body.activities)

    def get_activity(
        self,
        *,
        name: str | None = None,
        activity_id: ActivityId | None = None,
    ) -> Activity:
        """Find one exact activity local to this revision."""
        return _find_part(
            parts=self.activities,
            name=name,
            part_id=activity_id,
            identity_type=ActivityId,
        )

    @property
    def conditions(self) -> tuple[Condition, ...]:
        """Return the conditions captured on this revision."""
        return tuple(self.body.conditions)

    def get_condition(
        self,
        *,
        name: str | None = None,
        condition_id: ConditionId | None = None,
    ) -> Condition:
        """Find one exact condition local to this revision."""
        return _find_part(
            parts=self.conditions,
            name=name,
            part_id=condition_id,
            identity_type=ConditionId,
        )

    @property
    def events(self) -> tuple[Event, ...]:
        """Return the events captured on this revision."""
        return tuple(self.body.events)

    def get_event(
        self,
        *,
        name: str | None = None,
        event_id: EventId | None = None,
    ) -> Event:
        """Find one exact event local to this revision."""
        return _find_part(
            parts=self.events,
            name=name,
            part_id=event_id,
            identity_type=EventId,
        )

    @property
    def flows(self) -> tuple[Flow, ...]:
        """Return the flows captured on this revision."""
        return tuple(self.body.flows)

    def get_flow(
        self,
        *,
        name: str | None = None,
        flow_id: FlowId | None = None,
    ) -> Flow:
        """Find one exact flow local to this revision."""
        return _find_part(
            parts=self.flows,
            name=name,
            part_id=flow_id,
            identity_type=FlowId,
        )

    @property
    def gateways(self) -> tuple[Gateway, ...]:
        """Return the gateways captured on this revision."""
        return tuple(self.body.gateways)

    def get_gateway(
        self,
        *,
        name: str | None = None,
        gateway_id: GatewayId | None = None,
    ) -> Gateway:
        """Find one exact gateway local to this revision."""
        return _find_part(
            parts=self.gateways,
            name=name,
            part_id=gateway_id,
            identity_type=GatewayId,
        )

    @property
    def roles(self) -> tuple[Role, ...]:
        """Return the roles captured on this revision."""
        return tuple(self.body.roles)

    def get_role(
        self,
        *,
        name: str | None = None,
        role_id: RoleId | None = None,
    ) -> Role:
        """Find one exact role local to this revision."""
        return _find_part(
            parts=self.roles,
            name=name,
            part_id=role_id,
            identity_type=RoleId,
        )
