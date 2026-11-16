"""Identity for one approval record."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ApprovalId(OpaqueIdentifier):
    """Identity for one approval record."""
