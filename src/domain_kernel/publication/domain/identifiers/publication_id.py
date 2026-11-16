"""Identity for one publication."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class PublicationId(OpaqueIdentifier):
    """Identity for one publication."""
