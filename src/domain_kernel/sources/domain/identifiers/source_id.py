"""Identity for one acquired source."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class SourceId(OpaqueIdentifier):
    """Identity for one acquired source."""
