"""Runtime validation helpers shared across domain contexts."""

from collections.abc import Sequence


def is_non_string_sequence(value: object) -> bool:
    """Return whether a value is a sequence other than text or bytes."""
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
