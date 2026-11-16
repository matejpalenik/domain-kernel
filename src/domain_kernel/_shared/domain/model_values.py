"""Immutable nominal values shared by definition bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal, override

from domain_kernel.shared.contracts import Count
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence


# RFC 5646 section 2.1, with the grandfathered spellings listed there.
_LANGUAGE_TAG = re.compile(
    r"""
    (?:[a-z]{2,3}(?:-[a-z]{3}){0,3}|[a-z]{4}|[a-z]{5,8})
    (?:-[a-z]{4})?(?:-[a-z]{2}|-[0-9]{3})?
    (?P<variants>(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*)
    (?P<extensions>(?:-[0-9a-wy-z](?:-[a-z0-9]{2,8})+)*)
    (?:-x(?:-[a-z0-9]{1,8})+)?|x(?:-[a-z0-9]{1,8})+
    """,
    flags=re.VERBOSE,
)
_GRANDFATHERED_TAGS = frozenset(
    {
        "art-lojban",
        "cel-gaulish",
        "en-gb-oed",
        "i-ami",
        "i-bnn",
        "i-default",
        "i-enochian",
        "i-hak",
        "i-klingon",
        "i-lux",
        "i-mingo",
        "i-navajo",
        "i-pwn",
        "i-tao",
        "i-tay",
        "i-tsu",
        "no-bok",
        "no-nyn",
        "sgn-be-fr",
        "sgn-be-nl",
        "sgn-ch-de",
        "zh-guoyu",
        "zh-hakka",
        "zh-min",
        "zh-min-nan",
        "zh-xiang",
    }
)


@unique
class DataType(StrEnum):
    """Scalar and reference categories used by business definitions."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    REFERENCE = "reference"


type ScalarDataType = Literal[
    DataType.STRING,
    DataType.INTEGER,
    DataType.DECIMAL,
    DataType.BOOLEAN,
    DataType.DATE,
    DataType.DATETIME,
]


@dataclass(frozen=True, kw_only=True)
class _TextValue:
    value: str

    def __post_init__(self) -> None:
        """Preserve exact nonblank text, including internal whitespace."""
        field = type(self).__name__
        require_text(value=self.value, field=field)
        if self.value != self.value.strip():
            message = f"{field} cannot contain surrounding whitespace"
            raise ValueError(message)


@dataclass(frozen=True, kw_only=True)
class BusinessCode(_TextValue):
    """Case-sensitive identity for a member of a business vocabulary."""


@dataclass(frozen=True, kw_only=True)
class LabelText(_TextValue):
    """Display text for authored terminology."""


@dataclass(frozen=True, kw_only=True)
class MeaningText(_TextValue):
    """Prose stating the meaning of an authored value."""


@dataclass(frozen=True, kw_only=True)
class LanguageTag(_TextValue):
    """Structurally valid language tag for localized text."""

    @override
    def __post_init__(self) -> None:
        """Validate syntax without inferring or looking up language subtags."""
        super().__post_init__()
        value = self.value.lower()
        match = _LANGUAGE_TAG.fullmatch(value) if self.value.isascii() else None
        if match is None and value not in _GRANDFATHERED_TAGS:
            raise ValueError("LanguageTag must follow BCP 47 syntax")
        if match is not None and match.group("variants") is not None:
            variants = match.group("variants").split("-")[1:]
            singletons = [part for part in match.group("extensions").split("-") if len(part) == 1]
            if len(variants) != len(set(variants)) or len(singletons) != len(set(singletons)):
                raise ValueError("BCP 47 variants and extension singletons cannot repeat")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, kw_only=True)
class DecimalPrecision:
    """Maximum significant digits in a decimal value."""

    value: int

    def __post_init__(self) -> None:
        """Require a positive exact integer."""
        require_exact(value=self.value, expected=int, field="DecimalPrecision value")
        if self.value < 1:
            raise ValueError("DecimalPrecision value must be positive")


@dataclass(frozen=True, kw_only=True)
class DecimalScale:
    """Maximum fractional digits in a decimal value."""

    value: int

    def __post_init__(self) -> None:
        """Require a nonnegative exact integer."""
        require_exact(value=self.value, expected=int, field="DecimalScale value")
        if self.value < 0:
            raise ValueError("DecimalScale value must be nonnegative")


@unique
class CollectionKind(StrEnum):
    """Collection semantics for a business field."""

    SINGLE = "single"
    SET = "set"
    LIST = "list"


@unique
class Nullability(StrEnum):
    """Whether a present single-valued field may contain null."""

    FORBIDDEN = "forbidden"
    ALLOWED = "allowed"


@unique
class ValueSetMembership(StrEnum):
    """Whether the known business codes exhaust the permitted values."""

    CLOSED = "closed"
    OPEN = "open"


@unique
class LabelRole(StrEnum):
    """How a localized label may be used."""

    PREFERRED = "preferred"
    ALTERNATIVE = "alternative"
    HIDDEN = "hidden"


@dataclass(frozen=True, kw_only=True)
class LocalizedLabel:
    """One authored label and its explicit language and role."""

    text: LabelText
    language: LanguageTag
    role: LabelRole = LabelRole.PREFERRED

    def __post_init__(self) -> None:
        """Require a typed label, language and role."""
        require_exact(value=self.text, expected=LabelText, field="Label text")
        require_exact(value=self.language, expected=LanguageTag, field="Label language")
        require_exact(value=self.role, expected=LabelRole, field="Label role")


@dataclass(frozen=True, kw_only=True)
class LocalizedDescription:
    """One authored description in its declared language."""

    text: MeaningText
    language: LanguageTag

    def __post_init__(self) -> None:
        """Keep descriptive meaning separate from display labels."""
        require_exact(value=self.text, expected=MeaningText, field="Description text")
        require_exact(value=self.language, expected=LanguageTag, field="Description language")


@dataclass(frozen=True, kw_only=True)
class Terminology:
    """Localized labels and descriptions authored for one owner."""

    labels: Sequence[LocalizedLabel] = ()
    descriptions: Sequence[LocalizedDescription] = ()

    def __post_init__(self) -> None:
        """Snapshot inputs and enforce uniqueness within each language."""
        labels = snapshot_sequence(items=self.labels, item_type=LocalizedLabel, field="Labels")
        descriptions = snapshot_sequence(
            items=self.descriptions, item_type=LocalizedDescription, field="Descriptions"
        )
        preferred: set[LanguageTag] = set()
        roles: dict[tuple[LabelText, LanguageTag], LabelRole] = {}
        for label in labels:
            key = (label.text, label.language)
            if roles.setdefault(key, label.role) is not label.role:
                raise ValueError("Identical text and language cannot have conflicting label roles")
            if label.role is LabelRole.PREFERRED:
                if label.language in preferred:
                    raise ValueError("Each language may have at most one preferred label")
                preferred.add(label.language)
        if len({item.language for item in descriptions}) != len(descriptions):
            raise ValueError("Each language may have at most one description")
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "descriptions", descriptions)


_ZERO = Count(value=0)
_ONE = Count(value=1)


@dataclass(frozen=True, kw_only=True)
class CardinalityBounds:
    """Independent bounds for one direction of a relationship."""

    minimum: Count = _ZERO
    maximum: Count | None = _ONE

    def __post_init__(self) -> None:
        """Keep finite participation bounds in ascending order."""
        require_exact(value=self.minimum, expected=Count, field="Cardinality minimum")
        if self.maximum is not None:
            require_exact(value=self.maximum, expected=Count, field="Cardinality maximum")
            if self.minimum.value > self.maximum.value:
                raise ValueError("Cardinality maximum must be at least the minimum")


@dataclass(frozen=True, kw_only=True)
class RelationshipCardinality:
    """Directional participation bounds for a binary relationship."""

    outgoing: CardinalityBounds
    incoming: CardinalityBounds

    def __post_init__(self) -> None:
        """Require a distinct participation contract for each direction."""
        require_exact(value=self.outgoing, expected=CardinalityBounds, field="Outgoing cardinality")
        require_exact(value=self.incoming, expected=CardinalityBounds, field="Incoming cardinality")

    @classmethod
    def one_to_one(cls) -> RelationshipCardinality:
        """Allow zero or one relationship in each direction."""
        return cls(outgoing=CardinalityBounds(), incoming=CardinalityBounds())

    @classmethod
    def one_to_many(cls) -> RelationshipCardinality:
        """Allow unbounded outgoing relationships and at most one incoming."""
        return cls(outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds())

    @classmethod
    def many_to_one(cls) -> RelationshipCardinality:
        """Allow at most one outgoing relationship and unbounded incoming."""
        return cls(outgoing=CardinalityBounds(), incoming=CardinalityBounds(maximum=None))

    @classmethod
    def many_to_many(cls) -> RelationshipCardinality:
        """Allow unbounded relationships in each direction."""
        return cls(
            outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds(maximum=None)
        )


@dataclass(frozen=True, kw_only=True)
class DecimalFacets:
    """Exact optional limits on significant and fractional digits."""

    precision: DecimalPrecision | None = None
    scale: DecimalScale | None = None

    def __post_init__(self) -> None:
        """Validate optional limits without supplying implicit defaults."""
        if self.precision is None and self.scale is None:
            raise ValueError("DecimalFacets requires at least one limit")
        if self.precision is not None:
            require_exact(
                value=self.precision, expected=DecimalPrecision, field="Decimal precision"
            )
        if self.scale is not None:
            require_exact(value=self.scale, expected=DecimalScale, field="Decimal scale")
            if self.precision is not None and self.scale.value > self.precision.value:
                raise ValueError("Decimal scale cannot exceed precision")


def validate_decimal_value(*, value: Decimal, facets: DecimalFacets) -> None:
    """Check an exact finite decimal against its declared facets."""
    require_exact(value=value, expected=Decimal, field="Decimal value")
    require_exact(value=facets, expected=DecimalFacets, field="Decimal facets")
    if not value.is_finite():
        raise ValueError("Decimal value must be finite")
    _, digits, stored_exponent = value.as_tuple()
    exponent = int(stored_exponent)
    significant = len(digits)
    if value.is_zero():
        significant, exponent = 1, 0
    else:
        # Remove trailing zeros by adjusting the exact exponent without Context rounding.
        while digits[significant - 1] == 0:
            significant -= 1
            exponent += 1
    if facets.precision is not None and significant > facets.precision.value:
        raise ValueError("Decimal value exceeds precision")
    if facets.scale is not None and -exponent > facets.scale.value:
        raise ValueError("Decimal value exceeds scale")
