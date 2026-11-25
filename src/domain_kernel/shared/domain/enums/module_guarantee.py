"""The preservation guarantee reported for the selected signature."""

from enum import StrEnum, unique


@unique
class ModuleGuarantee(StrEnum):
    """The preservation guarantee reported for the selected signature."""

    SIGNATURE_ENTAILMENTS = "signature_entailments"
    NONE = "none"
