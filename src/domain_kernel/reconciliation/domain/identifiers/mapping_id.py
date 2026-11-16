"""Identity for one reconciliation mapping."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class MappingId(OpaqueIdentifier):
    """Identity for one reconciliation mapping."""
