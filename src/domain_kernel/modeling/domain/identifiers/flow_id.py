"""Nominal identity for a local flow definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class FlowId(OpaqueIdentifier):
    """Identify one inspected flow within its owning definition."""
