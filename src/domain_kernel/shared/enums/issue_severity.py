"""IssueSeverity choices for its owning domain."""

from enum import StrEnum, unique


@unique
class IssueSeverity(StrEnum):
    """Severity assigned to a structured diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
