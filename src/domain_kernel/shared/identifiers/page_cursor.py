"""Opaque cursor for a bound paginated query."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class PageCursor(OpaqueIdentifier):
    """Opaque cursor for a bound paginated query."""
