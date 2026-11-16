"""CaseKind choices for its owning domain."""

from enum import StrEnum, unique


@unique
class CaseKind(StrEnum):
    """Kind of review case."""

    PROPOSAL = "proposal"
    DEFINITION_REVISION = "definition_revision"
    DEFINITION_RETIREMENT = "definition_retirement"
    DEFINITION_RESTORATION = "definition_restoration"
    SOURCE_ALIGNMENT = "source_alignment"
    REFERENCE_ALIGNMENT = "reference_alignment"
    QUESTION = "question"
    CONFIRMATION = "confirmation"
    REFERENCE_PACK_CHANGE = "reference_pack_change"
    CHANGE_SET = "change_set"
