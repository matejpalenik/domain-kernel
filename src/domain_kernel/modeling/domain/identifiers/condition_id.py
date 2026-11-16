"""Nominal identity for a local condition definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ConditionId(OpaqueIdentifier):
    """Identify one inspected condition within its owning definition."""
