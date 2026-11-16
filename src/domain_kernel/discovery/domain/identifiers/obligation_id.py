"""Identity for one discovery obligation."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ObligationId(OpaqueIdentifier):
    """Identity for one discovery obligation."""
