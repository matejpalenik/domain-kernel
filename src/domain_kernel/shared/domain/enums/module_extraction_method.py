"""An explicit locality or reference extraction algorithm."""

from enum import StrEnum, unique


@unique
class ModuleExtractionMethod(StrEnum):
    """An explicit locality or reference extraction algorithm."""

    BOT = "bot"
    TOP = "top"
    STAR = "star"
    MIREOT = "mireot"
