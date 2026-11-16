"""Identity for one published domain-model bundle."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class BundleId(OpaqueIdentifier):
    """Identity for one published domain-model bundle."""
