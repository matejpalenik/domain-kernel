"""Describe a split or join in a process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import override
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.gateway_id import GatewayId
from domain_kernel.shared.domain.entities.part_snapshot import PartSnapshot
from domain_kernel.shared.domain.enums.gateway_direction import GatewayDirection
from domain_kernel.shared.domain.enums.gateway_kind import GatewayKind
from domain_kernel.shared.domain.naming import resolve_names
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True, init=False)
class Gateway(PartSnapshot):
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
        self._set_fields(
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
        RuntimeTypeValidation.require_exact(value=self.id, expected=GatewayId, field="Gateway ID")
        self._require_names(name=self.name, display_name=self.display_name)
        RuntimeTypeValidation.require_exact(
            value=self.kind, expected=GatewayKind, field="Gateway kind"
        )
        RuntimeTypeValidation.require_exact(
            value=self.direction, expected=GatewayDirection, field="Gateway direction"
        )
