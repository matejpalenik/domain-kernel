"""Cross-domain base for opaque identifier value objects."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=False)
class OpaqueIdentifier:
    """Store one exact, nonempty identifier string."""

    value: str

    def __post_init__(self) -> None:
        """Reject non-string, empty, or whitespace-padded identifiers."""
        if type(self.value) is not str:
            raise TypeError("Identifier must be a string")

        if not self.value:
            raise ValueError("Identifier cannot be empty")

        if self.value != self.value.strip():
            raise ValueError("Identifier cannot contain surrounding whitespace")
