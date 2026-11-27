"""SHA-256 identity for exact content bytes."""

from dataclasses import dataclass

from domain_kernel.shared.identifiers.opaque_identifier import OpaqueIdentifier
from domain_kernel.shared.validators.identifier_validation import IdentifierValidation


@dataclass(frozen=True)
class ContentHash(OpaqueIdentifier):
    """SHA-256 identity for exact content bytes."""

    def __post_init__(self) -> None:
        """Require the canonical SHA-256 representation."""
        super().__post_init__()

        IdentifierValidation.validate_sha256_identifier(self.value, name="ContentHash")
