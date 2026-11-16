"""Identity for one reference-pack pattern."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class PatternId(OpaqueIdentifier):
    """Identity for one reference-pack pattern."""
