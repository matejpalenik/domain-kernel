"""Nominal identity for an immutable source selection manifest."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class SourceManifestId(OpaqueIdentifier):
    """Identify one captured source selection."""
