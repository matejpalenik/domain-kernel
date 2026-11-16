"""Nominal identity of a durable action audit record."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class AuditId(OpaqueIdentifier):
    """Identify one immutable attributed event."""
