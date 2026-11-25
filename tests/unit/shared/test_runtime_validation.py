"""Preserve the runtime checks shared by SDK boundaries and domain records."""

import pytest

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation


class _Text(str):
    """A string subclass that static typing accepts where a string is expected."""

    __slots__: tuple[str, ...] = ()


def test_exact_type_does_not_accept_booleans_as_integers() -> None:
    with pytest.raises(TypeError, match=r"^Revision must be a int$"):
        RuntimeTypeValidation.require_exact(value=True, expected=int, field="Revision")


def test_text_requires_an_exact_nonblank_string() -> None:
    TextValidation.require_text(value="  catalog  ", field="Name")
    with pytest.raises(TypeError, match=r"^Name must be a str$"):
        TextValidation.require_text(value=_Text(" "), field="Name")
    with pytest.raises(ValueError, match=r"^Name must contain nonblank text$"):
        TextValidation.require_text(value=" \t\n", field="Name")


@pytest.mark.parametrize(
    "value",
    [
        "catalog",
        b"catalog",
        bytearray(b"catalog"),
        memoryview(b"catalog"),
        iter(("catalog",)),
    ],
)
def test_sequence_check_rejects_text_buffers_and_iterators(value: object) -> None:
    assert not SequenceValidation.is_non_string_sequence(value=value)


def test_sequence_snapshot_preserves_order_and_detaches_caller_storage() -> None:
    source = [4, 2]
    snapshot = SequenceValidation.snapshot_sequence(items=source, item_type=int, field="Parts")
    source[:] = [9]
    assert snapshot == (4, 2)


def test_sequence_snapshot_accepts_other_sequence_types() -> None:
    snapshot = SequenceValidation.snapshot_sequence(items=range(2), item_type=int, field="Parts")

    assert snapshot == (0, 1)


def test_sequence_snapshot_reports_the_invalid_item_position() -> None:
    with pytest.raises(TypeError, match=r"^Parts\[1\] must be a int$"):
        _ = SequenceValidation.snapshot_sequence(items=[4, True], item_type=int, field="Parts")


def test_sequence_snapshot_rejects_an_invalid_container_before_checking_items() -> None:
    with pytest.raises(TypeError, match=r"^Parts must be a sequence such as a list or tuple$"):
        _ = SequenceValidation.snapshot_sequence(items="catalog", item_type=str, field="Parts")
