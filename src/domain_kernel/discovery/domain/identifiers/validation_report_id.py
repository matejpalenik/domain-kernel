"""Identity for one validation report."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier


@dataclass(frozen=True)
class ValidationReportId(OpaqueIdentifier):
    """Identity for one validation report."""
