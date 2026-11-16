"""Identity for one coordinated change plan."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ChangePlanId(OpaqueIdentifier):
    """Identity for one coordinated change plan."""
