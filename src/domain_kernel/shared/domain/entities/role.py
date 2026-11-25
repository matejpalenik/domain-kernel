"""Describe a responsibility in a process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Never, override
from uuid import uuid4

from domain_kernel.modeling.domain.identifiers.role_id import RoleId
from domain_kernel.shared.domain.entities.part_snapshot import PartSnapshot
from domain_kernel.shared.domain.naming import resolve_names
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, init=False)
class Role(PartSnapshot):
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
        self._set_fields(
            attributes={
                "id": RoleId(value=uuid4().hex),
                "name": lookup,
                "display_name": label,
                "meaning": meaning,
                "evidence": self._snapshot_evidence(evidence=evidence),
            },
        )
        self._validate()

    @override
    @override
    def _validate(self) -> None:
        RuntimeTypeValidation.require_exact(value=self.id, expected=RoleId, field="Role ID")
        self._require_names(name=self.name, display_name=self.display_name)
        TextValidation.require_text(value=self.meaning, field="Role meaning")
        _ = self._snapshot_evidence(evidence=self.evidence)
