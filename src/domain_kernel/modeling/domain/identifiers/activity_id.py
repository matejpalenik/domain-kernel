"""Nominal identity for a local activity definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ActivityId(OpaqueIdentifier):
    """Identify one inspected activity within its owning definition."""
