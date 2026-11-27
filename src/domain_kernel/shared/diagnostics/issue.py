from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.diagnostics.issue_severity import IssueSeverity
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, init=False)
class Issue:
    """Sanitized diagnostic attached to validation and typed failures."""

    code: str
    path: tuple[str | int, ...]
    message: str
    severity: IssueSeverity

    def __init__(
        self,
        *,
        code: str,
        path: Sequence[str | int],
        message: str,
        severity: IssueSeverity = IssueSeverity.ERROR,
    ) -> None:
        """Validate fields and snapshot the caller-owned path."""
        if type(code) is not str:
            raise TypeError("Issue code must be a string")
        if not code:
            raise ValueError("Issue code must be a nonempty string")

        if type(message) is not str:
            raise TypeError("Issue message must be a string")
        if not message:
            raise ValueError("Issue message must be a nonempty string")

        if not SequenceValidation.is_non_string_sequence(value=path):
            raise TypeError("Issue path must be a sequence of strings and integers")

        if type(severity) is not IssueSeverity:
            raise TypeError("Issue severity must be an IssueSeverity member")

        path_snapshot = tuple(path)
        if any(type(part) not in (str, int) for part in path_snapshot):
            raise TypeError("Issue path elements must be exact strings or integers")

        object.__setattr__(self, "code", code)
        object.__setattr__(self, "path", path_snapshot)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "severity", severity)
