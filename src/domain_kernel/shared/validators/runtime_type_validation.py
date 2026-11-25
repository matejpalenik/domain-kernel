"""Exact runtime type checks shared by SDK boundaries and domain records."""


class RuntimeTypeValidation:
    """Validate concrete runtime types without accepting subclasses."""

    @staticmethod
    def require_exact(*, value: object, expected: type[object], field: str) -> None:
        """Raise TypeError with the field name if the runtime type is not exact."""
        if type(value) is not expected:
            message = f"{field} must be a {expected.__name__}"
            raise TypeError(message)
