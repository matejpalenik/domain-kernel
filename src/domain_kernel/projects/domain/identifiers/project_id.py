"""Identity for one project workspace."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ProjectId(OpaqueIdentifier):
    """Identity for one project workspace."""
