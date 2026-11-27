"""Stable lookup names and user-facing labels for authored records."""

import re
from string import punctuation
from typing import final

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

LOOKUP_NAME_PATTERN = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
_LOOKUP_NAME = re.compile(LOOKUP_NAME_PATTERN)
_NAME_SEPARATORS = re.compile(rf"[\s{re.escape(punctuation)}]+")


@final
class LookupNamingPolicy:
    """Resolve and validate names and selectors used by SDK lookups."""

    @staticmethod
    def require_lookup_name(*, name: str) -> None:
        """Validate an exact caller-supplied lookup name."""
        TextValidation.require_text(value=name, field="Lookup name")
        if _LOOKUP_NAME.fullmatch(name) is None:
            raise ValueError("Use a lookup name made of lowercase ASCII words separated by hyphens")

    @staticmethod
    def resolve_names(*, name: str | None, display_name: str | None) -> tuple[str, str]:
        """Resolve one stable lookup name and one display label at creation."""
        if name is not None:
            LookupNamingPolicy.require_lookup_name(name=name)
            if display_name is None:
                return name, name
            TextValidation.require_text(value=display_name, field="Display name")
            return name, display_name

        if display_name is None:
            raise ValueError("Supply a display name or an explicit name")
        TextValidation.require_text(value=display_name, field="Display name")

        derived = _NAME_SEPARATORS.sub("-", display_name.lower()).strip("-")
        if _LOOKUP_NAME.fullmatch(derived) is None:
            raise ValueError("Supply an explicit name for this display name")

        return derived, display_name

    @staticmethod
    def require_selector(*, name: str | None, item_id: object, id_type: type[object]) -> None:
        """Require one exact name or the specified nominal identifier."""
        if (name is None) == (item_id is None):
            raise ValueError("Supply exactly one name or ID")

        if name is not None:
            TextValidation.require_text(value=name, field="Lookup name")
        else:
            RuntimeTypeValidation.require_exact(value=item_id, expected=id_type, field="Lookup ID")
