"""Alignment identity used by reconciliation."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class AlignmentId(OpaqueIdentifier):
    """Alignment identity used by reconciliation."""
