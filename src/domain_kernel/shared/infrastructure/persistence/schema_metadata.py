"""Expose the complete workspace schema to both database adapters."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, final

from domain_kernel.shared.infrastructure.persistence.schema_row import SchemaRow

if TYPE_CHECKING:
    from sqlalchemy import MetaData


@final
class SchemaMetadata:
    """Load the complete workspace metadata for both database adapters."""

    @staticmethod
    def workspace() -> MetaData:
        """Return the workspace metadata after the operation adapters register their rows."""
        # Both schema managers can be used before opening a session.
        _ = import_module("domain_kernel.shared.infrastructure.persistence.sqlalchemy_transaction")
        return SchemaRow.metadata
