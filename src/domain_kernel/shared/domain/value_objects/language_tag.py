"""Structurally valid language tag for localized text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import override

from domain_kernel.shared.domain.value_objects.text_value import TextValue

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


@dataclass(frozen=True, kw_only=True)
class LanguageTag(TextValue):
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
