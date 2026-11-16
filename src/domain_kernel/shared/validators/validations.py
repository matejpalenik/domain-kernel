"""Validation shared by SHA-256-backed value objects."""

import re

_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


class IdentifierValidation:
    """Contains validators used for identifiers."""

    @staticmethod
    def validate_sha256_identifier(value: str, *, name: str) -> None:
        """Require the canonical lowercase SHA-256 spelling."""
        if _SHA256_PATTERN.fullmatch(value) is None:
            message = f"{name} must be a lowercase SHA-256 digest with 64 hexadecimal characters"
            raise ValueError(message)
