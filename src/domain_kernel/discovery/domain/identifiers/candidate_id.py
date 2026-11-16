"""Identity for one discovery candidate."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class CandidateId(OpaqueIdentifier):
    """Identity for one discovery candidate."""
