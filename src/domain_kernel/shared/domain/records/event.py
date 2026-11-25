"""Describe an event in a process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Never, override
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.event_id import EventId
from domain_kernel.shared.domain.enums.event_kind import EventKind
from domain_kernel.shared.domain.naming import resolve_names
from domain_kernel.shared.domain.records.part_snapshot import PartSnapshot
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, init=False)
class Event(PartSnapshot):
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
        self._set_fields(
            attributes={
                "id": EventId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "kind": kind,
                "evidence": self._snapshot_evidence(evidence=evidence),
            },
        )
        self._validate()

    @override
    def _validate(self) -> None:
        RuntimeTypeValidation.require_exact(value=self.id, expected=EventId, field="Event ID")
        self._require_names(name=self.name, display_name=self.display_name)
        RuntimeTypeValidation.require_exact(value=self.kind, expected=EventKind, field="Event kind")
        _ = self._snapshot_evidence(evidence=self.evidence)
