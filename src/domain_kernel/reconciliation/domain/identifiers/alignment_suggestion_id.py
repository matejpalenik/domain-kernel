"""Identity for one proposed alignment."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class AlignmentSuggestionId(OpaqueIdentifier):
    """Identity for one proposed alignment."""
