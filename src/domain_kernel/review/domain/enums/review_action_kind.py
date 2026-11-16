"""ReviewActionKind choices for its owning domain."""

from enum import StrEnum, unique


@unique
class ReviewActionKind(StrEnum):
    """Explicit action selected for a review proposal."""

    ACCEPT = "accept"
    EDIT_DEFINITION = "edit_definition"
    REJECT = "reject"
    MAP_TO_DEFINITION = "map_to_definition"
    MAP_TO_REFERENCE = "map_to_reference"
    LOCAL_EXTENSION = "local_extension"
    EXCLUDE = "exclude"
    DEFER = "defer"
    KEEP_NONBLOCKING_QUESTION = "keep_nonblocking_question"
    ANSWER_QUESTION = "answer_question"
    CONFIRM_STATEMENT = "confirm_statement"
