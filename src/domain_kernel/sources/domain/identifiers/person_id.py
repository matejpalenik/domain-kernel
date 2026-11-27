"""Identity for a person attributed across domain records."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class PersonId(OpaqueIdentifier):
    """Identity for a person attributed across domain records."""
