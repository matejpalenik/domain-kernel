"""Stable identity for a definition key."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class KeyId(OpaqueIdentifier):
    """Stable identity for a definition key."""
