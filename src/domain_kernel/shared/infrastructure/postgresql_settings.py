from __future__ import annotations

from dataclasses import dataclass, field

from domain_kernel.shared.validators.text_validation import TextValidation

_MAX_IDENTIFIER_BYTES = 63


@dataclass(frozen=True, kw_only=True)
class PostgreSQLSettings:
    """Exact operator-selected database URL, namespace, and operation limit."""

    dsn: str = field(repr=False)
    schema: str = "domain_kernel"
    concurrency: int = 4

    def __post_init__(self) -> None:
        """Capture settings without loading the driver or connecting to the server."""
        TextValidation.require_text(value=self.dsn, field="PostgreSQL DSN")
        TextValidation.require_text(value=self.schema, field="PostgreSQL schema")
        if "\x00" in self.schema or len(self.schema.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
            raise ValueError("Use a PostgreSQL schema name of at most 63 bytes")

        if type(self.concurrency) is not int or self.concurrency < 1:
            raise ValueError("Set positive PostgreSQL operation concurrency")
