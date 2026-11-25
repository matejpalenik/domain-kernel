"""Named identity requirement over direct attributes of an owning concept."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.key_id import KeyId
from domain_kernel.shared.domain.policies.naming import resolve_names
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, init=False)
class KeyDefinition:
    """Named identity requirement over direct attributes of an owning concept."""

    id: KeyId
    name: str
    display_name: str
    attributes: tuple[AttributeId, ...]

    def __init__(
        self,
        *,
        attributes: Sequence[AttributeId],
        display_name: str | None = None,
        name: str | None = None,
    ) -> None:
        """Give a business key its own opaque identity."""
        name, display_name = resolve_names(name=name, display_name=display_name)
        self._initialize(
            id=KeyId(value=uuid4().hex), name=name, display_name=display_name, attributes=attributes
        )

    @classmethod
    def _from_snapshot(
        cls,
        *,
        id: KeyId,  # noqa: A002 - Stored field name.
        name: str,
        display_name: str,
        attributes: Sequence[AttributeId],
    ) -> Self:
        instance = object.__new__(cls)
        instance._initialize(id=id, name=name, display_name=display_name, attributes=attributes)
        return instance

    def _initialize(
        self,
        *,
        id: KeyId,  # noqa: A002 - Stored field name.
        name: str,
        display_name: str,
        attributes: Sequence[AttributeId],
    ) -> None:
        RuntimeTypeValidation.require_exact(value=id, expected=KeyId, field="Key identity")
        _ = resolve_names(name=name, display_name=display_name)
        snapshot = SequenceValidation.snapshot_sequence(
            items=attributes, item_type=AttributeId, field="Key attributes"
        )
        if not snapshot:
            raise ValueError("A key requires at least one attribute")
        if len(set(snapshot)) != len(snapshot):
            raise ValueError("Key attributes must be distinct")
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "attributes", snapshot)
