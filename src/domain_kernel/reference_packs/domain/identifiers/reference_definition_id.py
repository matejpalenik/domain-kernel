"""Identity for one definition in a reference pack."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ReferenceDefinitionId(OpaqueIdentifier):
    """Identity for one definition in a reference pack."""
