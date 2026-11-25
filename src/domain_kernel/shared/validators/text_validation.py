"""Runtime validation for text fields."""

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


class TextValidation:
    """Validate text without normalizing it."""

    @staticmethod
    def require_text(*, value: str, field: str) -> None:
        """Require an exact str with nonblank text.

        Raises:
            TypeError: The value is not exactly a str.
            ValueError: The string is empty or contains only whitespace.
        """
        RuntimeTypeValidation.require_exact(value=value, expected=str, field=field)
        if not value.strip():
            message = f"{field} must contain nonblank text"
            raise ValueError(message)
