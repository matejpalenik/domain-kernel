"""Stable identity for a company model definition."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class DefinitionId(OpaqueIdentifier):
    """Stable identity for a company model definition."""
