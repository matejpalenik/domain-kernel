"""Nominal identity for a local gateway definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class GatewayId(OpaqueIdentifier):
    """Identify one inspected gateway within its owning definition."""
