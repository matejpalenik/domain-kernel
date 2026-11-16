"""Immutable authored process parts and their exact local identities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, ClassVar, Never, Protocol, Self, override, runtime_checkable
from uuid import uuid4

from domain_kernel._shared.domain.data_shapes import require_definition_reference
from domain_kernel._shared.domain.naming import require_lookup_name, resolve_names
from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.condition_id import ConditionId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.modeling.domain.identifiers.flow_id import FlowId
from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.validation import (
    is_non_string_sequence,
    require_exact,
    require_text,
    snapshot_sequence,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference, ModelScope


@unique
class EventKind(StrEnum):
    """Role of an event in the described process."""

    START = "start"
    END = "end"
    INTERMEDIATE = "intermediate"
    EXCEPTION = "exception"


@unique
class GatewayKind(StrEnum):
    """How the described process branches or rejoins."""

    EXCLUSIVE = "exclusive"
    PARALLEL = "parallel"


@unique
class GatewayDirection(StrEnum):
    """A gateway either splits or joins its incident flows."""

    SPLIT = "split"
    JOIN = "join"


@unique
class FlowKind(StrEnum):
    """Declared role of a connection between two named parts."""

    NORMAL = "normal"
    CONDITIONAL = "conditional"
    DEFAULT = "default"
    EXCEPTION = "exception"


def _evidence(*, evidence: Sequence[Never]) -> tuple[()]:
    if not is_non_string_sequence(evidence) or evidence:
        raise ValueError("Capture source revisions before attaching evidence")
    return ()


def _set_fields(*, value: object, attributes: dict[str, object]) -> None:
    for name, item in attributes.items():
        object.__setattr__(value, name, item)


class _PartSnapshot(ABC):
    """Share validated restoration for constructors that generate their IDs."""

    @classmethod
    def restore(cls, **attributes: object) -> Self:
        """Restore exact wire fields without recapturing references or generating IDs."""
        value = cls.__new__(cls)
        # The registry only calls restoration for the concrete dataclass part types.
        if not is_dataclass(value) or set(attributes) != {item.name for item in fields(value)}:
            raise ValueError("Use the exact stored process part fields")
        _set_fields(value=value, attributes=attributes)
        value._validate()  # noqa: SLF001 - Validate the restored concrete snapshot.
        return value

    @abstractmethod
    def _validate(self) -> None: ...


def _check_names(*, name: str, display_name: str) -> None:
    require_lookup_name(name=name)
    require_text(value=display_name, field="Part label")


@dataclass(frozen=True, kw_only=True, init=False)
class Role(_PartSnapshot):
    """A described responsibility carried out in a process."""

    id: RoleId
    name: str
    display_name: str
    meaning: str
    evidence: tuple[()]

    def __init__(
        self,
        *,
        meaning: str,
        display_name: str | None = None,
        name: str | None = None,
        evidence: Sequence[Never] = (),
    ) -> None:
        """Assign a new local identity to a named responsibility."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        _set_fields(
            value=self,
            attributes={
                "id": RoleId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "meaning": meaning,
                "evidence": _evidence(evidence=evidence),
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        require_exact(value=self.id, expected=RoleId, field="Role ID")
        _check_names(name=self.name, display_name=self.display_name)
        require_text(value=self.meaning, field="Role meaning")
        _ = _evidence(evidence=self.evidence)


@runtime_checkable
class InspectedDefinition(Protocol):
    """Identity and revision exposed by an inspected model-definition record."""

    @property
    def id(self) -> DefinitionId: ...

    @property
    def scope(self) -> ModelScope: ...

    @property
    def revision(self) -> int: ...


def _inspected(*, value: object) -> InspectedDefinition:
    if not isinstance(value, InspectedDefinition):
        raise TypeError("Use an inspected model definition or exact reference")
    require_exact(value=value.id, expected=DefinitionId, field="Inspected model definition ID")
    return value


def _model_edge(
    *, value: InspectedDefinition | DefinitionReference
) -> tuple[DefinitionReference, InspectedDefinition | None]:
    if isinstance(value, (DefinitionId, PinnedDefinitionReference, ReferenceDefinitionId)):
        require_definition_reference(value=value, field="Model definition")
        return value, None
    definition = _inspected(value=value)
    return definition.id, definition


def _model_edges(
    *,
    values: Sequence[InspectedDefinition | DefinitionReference],
) -> tuple[tuple[DefinitionReference, ...], tuple[InspectedDefinition, ...]]:
    if not is_non_string_sequence(values):
        raise TypeError("Use a sequence of model definitions or exact references")
    pairs = tuple(_model_edge(value=value) for value in values)
    return tuple(edge for edge, _ in pairs), tuple(
        binding for _, binding in pairs if binding is not None
    )


@dataclass(frozen=True, kw_only=True, init=False)
class Activity(_PartSnapshot):
    """A named step with reviewed business meaning for its edges."""

    id: ActivityId
    name: str
    display_name: str
    role_ids: tuple[RoleId, ...]
    input_ids: tuple[DefinitionReference, ...]
    output_ids: tuple[DefinitionReference, ...]
    decision_id: DefinitionReference | None
    evidence: tuple[()]
    _definitions: ClassVar[tuple[InspectedDefinition, ...]] = ()
    _roles: ClassVar[tuple[Role, ...]] = ()

    def __init__(  # noqa: PLR0913 - Explicit authoring edges and label.
        self,
        *,
        display_name: str | None = None,
        name: str | None = None,
        roles: Sequence[Role | RoleId] = (),
        inputs: Sequence[InspectedDefinition | DefinitionReference] = (),
        outputs: Sequence[InspectedDefinition | DefinitionReference] = (),
        decision: InspectedDefinition | DefinitionReference | None = None,
        evidence: Sequence[Never] = (),
    ) -> None:
        """Capture exact roles, information and the optional decision."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        if not is_non_string_sequence(roles):
            raise TypeError("Use a sequence of roles or role IDs")
        input_ids, input_records = _model_edges(values=inputs)
        output_ids, output_records = _model_edges(values=outputs)
        decision_id, decision_record = (
            (None, None) if decision is None else _model_edge(value=decision)
        )
        _set_fields(
            value=self,
            attributes={
                "id": ActivityId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "role_ids": tuple(role.id if isinstance(role, Role) else role for role in roles),
                "input_ids": input_ids,
                "output_ids": output_ids,
                "decision_id": decision_id,
                "evidence": _evidence(evidence=evidence),
                "_definitions": (
                    *input_records,
                    *output_records,
                    *((decision_record,) if decision_record else ()),
                ),
                "_roles": tuple(role for role in roles if isinstance(role, Role)),
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        require_exact(value=self.id, expected=ActivityId, field="Activity ID")
        _check_names(name=self.name, display_name=self.display_name)
        role_ids = snapshot_sequence(items=self.role_ids, item_type=RoleId, field="Activity roles")
        if len(set(role_ids)) != len(role_ids):
            raise ValueError("Use distinct activity roles")
        for refs in (self.input_ids, self.output_ids):
            if not is_non_string_sequence(refs):
                raise TypeError("Use a sequence of exact model definition references")
            for ref in refs:
                require_definition_reference(value=ref, field="Activity information")
            if len(set(refs)) != len(refs):
                raise ValueError("Use distinct activity information references")
        if self.decision_id is not None:
            require_definition_reference(value=self.decision_id, field="Activity decision")
        _ = _evidence(evidence=self.evidence)
        object.__setattr__(self, "role_ids", role_ids)
        object.__setattr__(self, "input_ids", tuple(self.input_ids))
        object.__setattr__(self, "output_ids", tuple(self.output_ids))

    @property
    def referenced_definitions(self) -> tuple[InspectedDefinition, ...]:
        """Return author-supplied inspected snapshots for exact plan bindings."""
        return self._definitions

    @property
    def referenced_roles(self) -> tuple[Role, ...]:
        """Return author-supplied roles for local membership verification."""
        return self._roles


@dataclass(frozen=True, kw_only=True, init=False)
class Event(_PartSnapshot):
    """A named event in the descriptive process graph."""

    id: EventId
    name: str
    display_name: str
    kind: EventKind
    evidence: tuple[()]

    def __init__(
        self,
        *,
        kind: EventKind,
        display_name: str | None = None,
        name: str | None = None,
        evidence: Sequence[Never] = (),
    ) -> None:
        """Create one identified start, end, intermediate or exception event."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        _set_fields(
            value=self,
            attributes={
                "id": EventId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "kind": kind,
                "evidence": _evidence(evidence=evidence),
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        require_exact(value=self.id, expected=EventId, field="Event ID")
        _check_names(name=self.name, display_name=self.display_name)
        require_exact(value=self.kind, expected=EventKind, field="Event kind")
        _ = _evidence(evidence=self.evidence)


@dataclass(frozen=True, kw_only=True, init=False)
class Gateway(_PartSnapshot):
    """An identified split or join in a process description."""

    id: GatewayId
    name: str
    display_name: str
    kind: GatewayKind
    direction: GatewayDirection

    def __init__(
        self,
        *,
        kind: GatewayKind,
        direction: GatewayDirection,
        display_name: str | None = None,
        name: str | None = None,
    ) -> None:
        """Create one exclusive or parallel gateway."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        _set_fields(
            value=self,
            attributes={
                "id": GatewayId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "kind": kind,
                "direction": direction,
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        require_exact(value=self.id, expected=GatewayId, field="Gateway ID")
        _check_names(name=self.name, display_name=self.display_name)
        require_exact(value=self.kind, expected=GatewayKind, field="Gateway kind")
        require_exact(value=self.direction, expected=GatewayDirection, field="Gateway direction")


@dataclass(frozen=True, kw_only=True, init=False)
class Condition(_PartSnapshot):
    """An inert condition referencing owner-local input symbols."""

    id: ConditionId
    name: str
    display_name: str
    description: str
    input_ids: tuple[str, ...]
    expression: str
    evidence: tuple[()]

    def __init__(  # noqa: PLR0913 - Keep the condition's authored fields explicit.
        self,
        *,
        description: str,
        expression: str,
        display_name: str | None = None,
        name: str | None = None,
        input_ids: Sequence[str] = (),
        evidence: Sequence[Never] = (),
    ) -> None:
        """Capture declared inputs and inert condition text under a stable local ID."""
        lookup, label = resolve_names(name=name, display_name=display_name)
        _set_fields(
            value=self,
            attributes={
                "id": ConditionId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "description": description,
                "input_ids": input_ids,
                "expression": expression,
                "evidence": _evidence(evidence=evidence),
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        require_exact(value=self.id, expected=ConditionId, field="Condition ID")
        _check_names(name=self.name, display_name=self.display_name)
        require_text(value=self.description, field="Condition description")
        require_text(value=self.expression, field="Condition expression")
        inputs = snapshot_sequence(items=self.input_ids, item_type=str, field="Condition inputs")
        for item in inputs:
            require_text(value=item, field="Condition input symbol")
        if len(set(inputs)) != len(inputs):
            raise ValueError("Use distinct condition input symbols")
        _ = _evidence(evidence=self.evidence)
        object.__setattr__(self, "input_ids", inputs)


type ProcessNodeId = ActivityId | EventId | GatewayId
type ProcessNode = Activity | Event | Gateway


@dataclass(frozen=True, kw_only=True, init=False)
class Flow(_PartSnapshot):
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
        lookup, label = resolve_names(name=name, display_name=display_name)
        _set_fields(
            value=self,
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
                "evidence": _evidence(evidence=evidence),
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
        require_exact(value=self.id, expected=FlowId, field="Flow ID")
        _check_names(name=self.name, display_name=self.display_name)
        require_exact(value=self.kind, expected=FlowKind, field="Flow kind")
        if any(
            type(item) not in (ActivityId, EventId, GatewayId)
            for item in (self.source_id, self.target_id)
        ):
            raise TypeError("Use exact typed process node IDs")
        if self.condition_id is not None:
            require_exact(value=self.condition_id, expected=ConditionId, field="Condition ID")
        if (self.condition_id is not None) != (self.kind is FlowKind.CONDITIONAL):
            raise ValueError("Only a conditional flow requires an explicit condition")
        _ = _evidence(evidence=self.evidence)

    @property
    def referenced_nodes(self) -> tuple[ProcessNode, ...]:
        """Return supplied node snapshots for exact local verification."""
        return self._nodes

    @property
    def referenced_conditions(self) -> tuple[Condition, ...]:
        """Return supplied condition snapshots for exact local verification."""
        return self._conditions
