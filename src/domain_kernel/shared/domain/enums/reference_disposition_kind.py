"""Review disposition of a definition against its selected reference context."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ReferenceDispositionKind(StrEnum):
    """Review disposition of a definition against its selected reference context."""

    MAPPED = "mapped"
    LOCAL_EXTENSION = "local_extension"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"
    STALE = "stale"
