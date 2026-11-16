"""Identity for one review decision."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class DecisionId(OpaqueIdentifier):
    """Identity for one review decision."""
