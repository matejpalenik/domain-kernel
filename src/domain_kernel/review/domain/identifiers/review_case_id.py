"""Review domain identifiers."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ReviewCaseId(OpaqueIdentifier):
    """Opaque identity for one review case."""
