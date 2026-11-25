from dataclasses import FrozenInstanceError
from inspect import Parameter, signature

import pytest

from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId


class StringSubclass(str):
    """String subclass used to check exact-string validation."""

    __slots__: tuple[str, ...] = ()


def test_review_case_id_accepts_a_nonempty_value() -> None:
    identifier = ReviewCaseId(value="case-17")

    assert identifier.value == "case-17"


def test_review_case_id_accepts_a_positional_argument_value() -> None:
    identifier = ReviewCaseId("case-17")

    assert identifier.value == "case-17"


def test_review_case_id_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match=r"^Identifier cannot be empty$"):
        _ = ReviewCaseId(value="")


@pytest.mark.parametrize("value", [" case-17", "case-17 "])
def test_review_case_id_rejects_surrounding_whitespace(value: str) -> None:
    with pytest.raises(
        ValueError,
        match=r"^Identifier cannot contain surrounding whitespace$",
    ):
        _ = ReviewCaseId(value=value)


def test_review_case_id_rejects_str_subclasses() -> None:
    with pytest.raises(TypeError):
        _ = ReviewCaseId(value=StringSubclass("case-17"))


def test_review_case_id_is_immutable() -> None:
    identifier = ReviewCaseId(value="case-17")

    with pytest.raises(FrozenInstanceError):
        setattr(identifier, "value", "case-18")  # noqa: B010


def test_review_case_id_constructor_accepts_positional_or_keyword_value() -> None:
    value_parameter = signature(ReviewCaseId).parameters["value"]

    assert value_parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
