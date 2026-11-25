"""Runtime validation and immutable snapshots for sequence fields."""

from collections.abc import Sequence

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


class SequenceValidation:
    """Validate sequences that represent collections rather than text or bytes."""

    @staticmethod
    def is_non_string_sequence(*, value: object) -> bool:
        """Return whether a value is a sequence other than text or a byte buffer."""
        return isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray, memoryview)
        )

    @staticmethod
    def snapshot_sequence[T](
        *, items: Sequence[T], item_type: type[T], field: str
    ) -> tuple[T, ...]:
        """Return an ordered tuple detached from the caller's sequence.

        Raises:
            TypeError: The input is not a non-string sequence or an item does not
                have the exact item type.
        """
        if not SequenceValidation.is_non_string_sequence(value=items):
            message = f"{field} must be a sequence such as a list or tuple"
            raise TypeError(message)
        snapshot = tuple(items)
        for index, item in enumerate(snapshot):
            RuntimeTypeValidation.require_exact(
                value=item, expected=item_type, field=f"{field}[{index}]"
            )
        return snapshot
