"""Preserve the exact spelling of an absolute resource identifier."""

import re
from dataclasses import dataclass
from typing import Literal

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation

_IRI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


_INVALID_IRI_CHAR = re.compile(r'[\x00-\x20\x7f-\x9f\ud800-\udfff<>"{}|\\^`]|%(?![0-9A-Fa-f]{2})')


@dataclass(frozen=True, kw_only=True)
class Iri:
    """Preserve the exact spelling of an absolute resource identifier."""

    value: str
    kind: Literal["iri"] = "iri"

    def __post_init__(self) -> None:
        """Reject relative or malformed IRIs without dereferencing resources."""
        TextValidation.require_text(value=self.value, field="IRI")
        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="IRI kind")
        if self.kind != "iri":
            raise ValueError("IRI kind must be 'iri'")
        if (
            _IRI_SCHEME.match(self.value) is None
            or _INVALID_IRI_CHAR.search(self.value)
            or any(character.isspace() for character in self.value)
        ):
            raise ValueError("Use an absolute IRI with a valid scheme and spelling")
