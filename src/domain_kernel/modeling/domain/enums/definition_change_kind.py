"""DefinitionChangeKind choices for its owning domain."""

from enum import StrEnum, unique


@unique
class DefinitionChangeKind(StrEnum):
    """Kinds of definition changes that can be proposed."""

    ADD = "add"
    EDIT = "edit"
    RETIRE = "retire"
    REMOVE = "remove"
    MERGE = "merge"
    RELATE = "relate"
    SEPARATE = "separate"
    REUSE = "reuse"
