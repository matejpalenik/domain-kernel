"""DefinitionStatus choices for its owning domain."""

from enum import StrEnum, unique


@unique
class DefinitionStatus(StrEnum):
    """Lifecycle state of a model definition."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    RETIRED = "retired"
