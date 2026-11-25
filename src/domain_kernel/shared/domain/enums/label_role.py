"""How a localized label may be used."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class LabelRole(StrEnum):
    """How a localized label may be used."""

    PREFERRED = "preferred"
    ALTERNATIVE = "alternative"
    HIDDEN = "hidden"
