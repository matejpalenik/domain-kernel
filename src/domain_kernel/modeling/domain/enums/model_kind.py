"""ModelKind choices for their owning domain."""

from enum import StrEnum, unique


@unique
class ModelKind(StrEnum):
    """Distinguish descriptions of existing behavior from proposed designs."""

    OBSERVED = "observed"
    PROPOSED = "proposed"
