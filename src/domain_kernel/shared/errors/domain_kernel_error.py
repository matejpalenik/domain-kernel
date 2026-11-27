from __future__ import annotations


class DomainKernelError(Exception):
    """Base for typed SDK failures with stable machine-readable codes."""

    code: str
    retryable: bool

    def __init__(self, *, message: str, code: str, retryable: bool = False) -> None:
        """Initialize a sanitized message and stable failure metadata."""
        message = DomainKernelError._validated_nonempty_string(message, name="Error message")
        code = DomainKernelError._validated_nonempty_string(code, name="Error code")
        retryable = DomainKernelError._validated_bool(retryable, name="retryable")

        super().__init__(message)
        self.code = code
        self.retryable = retryable

    @staticmethod
    def _validated_nonempty_string(value: object, *, name: str) -> str:
        """Return a nonempty exact string suitable for error metadata."""
        if type(value) is not str:
            message = f"{name} must be a string"
            raise TypeError(message)

        if not value:
            message = f"{name} must be a nonempty string"
            raise ValueError(message)

        return value

    @staticmethod
    def _validated_bool(value: object, *, name: str) -> bool:
        """Return an exact boolean for the error's retry flag."""
        if type(value) is not bool:
            message = f"{name} must be a bool"
            raise TypeError(message)

        return value
