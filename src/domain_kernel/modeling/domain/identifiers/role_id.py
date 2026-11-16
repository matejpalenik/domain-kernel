"""Nominal identity for a local role definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class RoleId(OpaqueIdentifier):
    """Identify one inspected role within its owning definition."""
