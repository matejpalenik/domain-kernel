"""Identity for one discovery draft."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class DiscoveryDraftId(OpaqueIdentifier):
    """Identity for one discovery draft."""
