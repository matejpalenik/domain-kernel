"""Independent budgets for supplied bytes, closure expansion and parsing time."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class OntologyLimits:
    """Independent budgets for supplied bytes, closure expansion and parsing time."""

    max_bytes: int = 64 * 1024 * 1024
    max_documents: int = 256
    max_statements: int = 1_000_000
    timeout_ms: int = 60_000

    def __post_init__(self) -> None:
        """Require positive finite integer limits."""
        for value in (self.max_bytes, self.max_documents, self.max_statements, self.timeout_ms):
            if type(value) is not int or value < 1:
                raise ValueError("Set positive integer ontology limits")
