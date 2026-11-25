"""A closed or open vocabulary of distinct known codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.enums.value_set_membership import ValueSetMembership
from domain_kernel.shared.domain.validators.definition_parts_validation import (
    DefinitionPartsValidation,
)
from domain_kernel.shared.domain.value_objects.value_set_member import ValueSetMember
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class ValueSetDefinition:
    """A closed or open vocabulary of distinct known codes."""

    membership: ValueSetMembership
    members: Sequence[ValueSetMember]
    kind: Literal[DefinitionKind.VALUE_SET] = DefinitionKind.VALUE_SET

    def __post_init__(self) -> None:
        """Keep ordered member metadata with distinct exact codes."""
        DefinitionPartsValidation.require_body_kind(
            kind=self.kind, expected=DefinitionKind.VALUE_SET
        )
        RuntimeTypeValidation.require_exact(
            value=self.membership, expected=ValueSetMembership, field="Membership"
        )
        members = SequenceValidation.snapshot_sequence(
            items=self.members, item_type=ValueSetMember, field="Members"
        )
        if not members:
            raise ValueError("A value set requires at least one known code")
        if len({item.code for item in members}) != len(members):
            raise ValueError("Value-set codes must be distinct")
        object.__setattr__(self, "members", members)
