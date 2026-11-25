"""Restore identified parts shared by process and decision definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Self

from domain_kernel.shared.domain.naming import require_lookup_name
from domain_kernel.shared.validation import is_non_string_sequence, require_text

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Never


class PartSnapshot(ABC):
    """Restore exact wire fields without regenerating IDs or capturing references."""

    @classmethod
    def restore(cls, **attributes: object) -> Self:
        """Restore and validate the stored fields of a concrete part."""
        value = cls.__new__(cls)
        if not is_dataclass(value) or set(attributes) != {item.name for item in fields(value)}:
            raise ValueError("Use the exact stored process part fields")
        cls._set_fields(value, attributes=attributes)
        cls._validate(value)
        return value

    def _set_fields(self, *, attributes: dict[str, object]) -> None:
        for name, item in attributes.items():
            object.__setattr__(self, name, item)

    @staticmethod
    def _require_names(*, name: str, display_name: str) -> None:
        require_lookup_name(name=name)
        require_text(value=display_name, field="Part label")

    @staticmethod
    def _snapshot_evidence(*, evidence: Sequence[Never]) -> tuple[()]:
        if not is_non_string_sequence(evidence) or evidence:
            raise ValueError("Capture source revisions before attaching evidence")
        return ()

    @abstractmethod
    def _validate(self) -> None: ...
