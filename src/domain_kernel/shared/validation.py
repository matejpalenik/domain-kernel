"""Runtime validation helpers shared across domain contexts."""

from collections.abc import Sequence


def is_non_string_sequence(value: object) -> bool:
    """Return whether a value is a sequence other than text or a byte buffer."""
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    )


def require_exact(*, value: object, expected: type[object], field: str) -> None:
    """Require the declared runtime type and identify the invalid field."""
    if type(value) is not expected:
        message = f"{field} must be a {expected.__name__}"
        raise TypeError(message)


def snapshot_sequence[T](*, items: Sequence[T], item_type: type[T], field: str) -> tuple[T, ...]:
    """Detach a typed sequence from its caller after checking each element."""
    if not is_non_string_sequence(items):
        message = f"{field} must be a sequence such as a list or tuple"
        raise TypeError(message)
    snapshot = tuple(items)
    for index, item in enumerate(snapshot):
        require_exact(value=item, expected=item_type, field=f"{field}[{index}]")
    return snapshot


def require_text(*, value: str, field: str) -> None:
    """Require an exact Unicode string with nonblank text."""
    require_exact(value=value, expected=str, field=field)
    if not value.strip():
        message = f"{field} must contain nonblank text"
        raise ValueError(message)
