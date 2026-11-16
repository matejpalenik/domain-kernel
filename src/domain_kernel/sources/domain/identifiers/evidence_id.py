"""Identity for one evidence record."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class EvidenceId(OpaqueIdentifier):
    """Identity for one evidence record."""
