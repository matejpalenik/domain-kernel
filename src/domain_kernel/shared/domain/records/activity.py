"""Describe an activity and its referenced business definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Never, override
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.activity_id import ActivityId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.contracts import PinnedDefinitionReference
from domain_kernel.shared.domain.data_shapes import require_definition_reference
from domain_kernel.shared.domain.naming import resolve_names
from domain_kernel.shared.domain.protocols.inspected_definition import (
    InspectedDefinition,
)
from domain_kernel.shared.domain.records.part_snapshot import PartSnapshot
from domain_kernel.shared.domain.records.role import Role
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.shared.contracts import DefinitionReference


@dataclass(frozen=True, kw_only=True, init=False)
class Activity(PartSnapshot):
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
        if not SequenceValidation.is_non_string_sequence(value=roles):
            raise TypeError("Use a sequence of roles or role IDs")
        input_ids, input_records = _model_edges(values=inputs)
        output_ids, output_records = _model_edges(values=outputs)
        decision_id, decision_record = (
            (None, None) if decision is None else _model_edge(value=decision)
        )
        self._set_fields(
            attributes={
                "id": ActivityId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "role_ids": tuple(role.id if isinstance(role, Role) else role for role in roles),
                "input_ids": input_ids,
                "output_ids": output_ids,
                "decision_id": decision_id,
                "evidence": self._snapshot_evidence(evidence=evidence),
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
        RuntimeTypeValidation.require_exact(value=self.id, expected=ActivityId, field="Activity ID")
        self._require_names(name=self.name, display_name=self.display_name)
        role_ids = SequenceValidation.snapshot_sequence(
            items=self.role_ids, item_type=RoleId, field="Activity roles"
        )
        if len(set(role_ids)) != len(role_ids):
            raise ValueError("Use distinct activity roles")
        for refs in (self.input_ids, self.output_ids):
            if not SequenceValidation.is_non_string_sequence(value=refs):
                raise TypeError("Use a sequence of exact model definition references")
            for ref in refs:
                require_definition_reference(value=ref, field="Activity information")
            if len(set(refs)) != len(refs):
                raise ValueError("Use distinct activity information references")
        if self.decision_id is not None:
            require_definition_reference(value=self.decision_id, field="Activity decision")
        _ = self._snapshot_evidence(evidence=self.evidence)
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


def _inspected(*, value: object) -> InspectedDefinition:
    if not isinstance(value, InspectedDefinition):
        raise TypeError("Use an inspected model definition or exact reference")
    RuntimeTypeValidation.require_exact(
        value=value.id, expected=DefinitionId, field="Inspected model definition ID"
    )
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
    if not SequenceValidation.is_non_string_sequence(value=values):
        raise TypeError("Use a sequence of model definitions or exact references")
    pairs = tuple(_model_edge(value=value) for value in values)
    return tuple(edge for edge, _ in pairs), tuple(
        binding for _, binding in pairs if binding is not None
    )
