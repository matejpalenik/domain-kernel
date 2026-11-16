"""CaseStatus choices for its owning domain."""

from enum import StrEnum, unique


@unique
class CaseStatus(StrEnum):
    """Resolution state of a review case."""

    PENDING = "pending"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    REVIEWED_NONBLOCKING = "reviewed_nonblocking"
    SUPERSEDED = "superseded"
