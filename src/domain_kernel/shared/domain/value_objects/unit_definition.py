"""Reusable unit with an optional symbol and an exact authored term."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
from domain_kernel.shared.domain.validators.definition_parts_validation import (
    DefinitionPartsValidation,
)
from domain_kernel.shared.domain.value_objects.ontology_term_reference import (
    OntologyTermReference,
    require_unit_term,
)
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class UnitDefinition:
    """Reusable unit with an optional symbol and an exact authored term."""

    symbol: str | None = None
    ontology_term: OntologyTermReference | None = None
    kind: Literal[DefinitionKind.UNIT] = DefinitionKind.UNIT

    def __post_init__(self) -> None:
        """Preserve optional display and declared external identity separately."""
        DefinitionPartsValidation.require_body_kind(kind=self.kind, expected=DefinitionKind.UNIT)
        if self.symbol is not None:
            TextValidation.require_text(value=self.symbol, field="Unit symbol")
        if self.ontology_term is not None:
            require_unit_term(term=self.ontology_term)
