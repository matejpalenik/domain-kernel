"""Identity for one discovery run."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class DiscoveryRunId(OpaqueIdentifier):
    """Identity for one discovery run."""
