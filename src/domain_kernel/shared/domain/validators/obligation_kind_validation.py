"""Validate consumer obligation discriminators."""

from __future__ import annotations

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


class ObligationKindValidation:
    """Check the kind shared by a consumer obligation and its stored form."""

    @staticmethod
    def require_kind(*, value: str, expected: str) -> None:
        """Require the declared consumer obligation discriminator."""
        RuntimeTypeValidation.require_exact(value=value, expected=str, field="Obligation kind")
        if value != expected:
            raise ValueError("Select the declared consumer obligation kind")
