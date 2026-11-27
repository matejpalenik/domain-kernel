from decimal import Decimal, localcontext

import pytest

from domain_kernel.shared.domain.enums.label_role import LabelRole
from domain_kernel.shared.domain.value_objects.business_code import BusinessCode
from domain_kernel.shared.domain.value_objects.cardinality_bounds import CardinalityBounds
from domain_kernel.shared.domain.value_objects.count import Count
from domain_kernel.shared.domain.value_objects.decimal_facets import DecimalFacets
from domain_kernel.shared.domain.value_objects.decimal_precision import DecimalPrecision
from domain_kernel.shared.domain.value_objects.decimal_scale import DecimalScale
from domain_kernel.shared.domain.value_objects.label_text import LabelText
from domain_kernel.shared.domain.value_objects.language_tag import LanguageTag
from domain_kernel.shared.domain.value_objects.localized_description import LocalizedDescription
from domain_kernel.shared.domain.value_objects.localized_label import LocalizedLabel
from domain_kernel.shared.domain.value_objects.meaning_text import MeaningText
from domain_kernel.shared.domain.value_objects.terminology import Terminology


@pytest.mark.parametrize("value", ["", " provider", "provider "])
def test_business_codes_reject_blank_or_surrounding_space(value: str) -> None:
    with pytest.raises(ValueError, match="BusinessCode"):
        _ = BusinessCode(value=value)


@pytest.mark.parametrize("value", ["FR-Latn-CA", "i-klingon", "x-local", "en-u-ca-gregory"])
def test_language_tags_are_stored_in_lowercase(value: str) -> None:
    assert LanguageTag(value=value).value == value.lower()


@pytest.mark.parametrize("value", ["en_US", "en--US", "en-a", "en-å", "en-abcdefghi"])
def test_malformed_language_tags_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="BCP 47"):
        _ = LanguageTag(value=value)


def test_terminology_detaches_inputs_and_rejects_conflicting_labels() -> None:
    chosen = LocalizedLabel(text=LabelText(value="Provider"), language=LanguageTag(value="en"))
    labels = [chosen]
    terminology = Terminology(labels=labels)
    labels.clear()

    assert terminology.labels == (chosen,)
    conflicting = LocalizedLabel(
        text=chosen.text, language=LanguageTag(value="EN"), role=LabelRole.HIDDEN
    )
    with pytest.raises(ValueError, match="conflicting"):
        _ = Terminology(labels=[chosen, conflicting])


def test_terminology_limits_preferred_labels_and_descriptions_by_language() -> None:
    language = LanguageTag(value="en")
    with pytest.raises(ValueError, match="preferred"):
        _ = Terminology(
            labels=[
                LocalizedLabel(text=LabelText(value="Provider"), language=language),
                LocalizedLabel(text=LabelText(value="Supplier"), language=language),
            ],
        )
    with pytest.raises(ValueError, match="description"):
        _ = Terminology(
            descriptions=[
                LocalizedDescription(text=MeaningText(value="First"), language=language),
                LocalizedDescription(text=MeaningText(value="Second"), language=language),
            ],
        )


def test_decimal_facets_reject_empty_or_contradictory_limits() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _ = DecimalFacets()
    with pytest.raises(ValueError, match="scale"):
        _ = DecimalFacets(precision=DecimalPrecision(value=2), scale=DecimalScale(value=3))


def test_decimal_facets_check_exact_normalized_digits_independently_of_context() -> None:
    facets = DecimalFacets(precision=DecimalPrecision(value=4), scale=DecimalScale(value=2))
    with localcontext() as context:
        context.prec = 1
        DecimalFacets.validate_decimal_value(value=Decimal("12.3400"), facets=facets)
        with pytest.raises(ValueError, match="precision"):
            DecimalFacets.validate_decimal_value(value=Decimal("123.45"), facets=facets)
        with pytest.raises(ValueError, match="scale"):
            DecimalFacets.validate_decimal_value(value=Decimal("0.001"), facets=facets)
        with pytest.raises(ValueError, match="finite"):
            DecimalFacets.validate_decimal_value(value=Decimal("NaN"), facets=facets)


def test_relationship_bounds_reject_a_maximum_below_the_minimum() -> None:
    with pytest.raises(ValueError, match="maximum"):
        _ = CardinalityBounds(minimum=Count(value=2), maximum=Count(value=1))
