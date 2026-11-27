"""An exact RDF literal with optional datatype or language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.domain.value_objects.language_tag import LanguageTag
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class RdfLiteral:
    """An exact RDF literal with optional datatype or language."""

    value: str
    datatype: Iri | None = None
    language: str | None = None
    kind: Literal["literal"] = "literal"

    def __post_init__(self) -> None:
        """Retain lexical values and canonicalize a well-formed language tag."""
        RuntimeTypeValidation.require_exact(value=self.value, expected=str, field="Literal value")

        RuntimeTypeValidation.require_exact(value=self.kind, expected=str, field="Literal kind")
        if self.kind != "literal":
            raise ValueError("Use the RDF literal discriminator")

        if self.datatype is not None:
            RuntimeTypeValidation.require_exact(
                value=self.datatype, expected=Iri, field="Literal datatype"
            )

        if self.language is not None:
            if self.datatype is not None:
                raise ValueError("Choose a datatyped or language-tagged literal")

            object.__setattr__(self, "language", LanguageTag(value=self.language).value)
