"""Nominal identity for a local event definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class EventId(OpaqueIdentifier):
    """Identify one inspected event within its owning definition."""
