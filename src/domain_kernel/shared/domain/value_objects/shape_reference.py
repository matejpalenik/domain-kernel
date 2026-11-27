"""One typed edge plus its path within the owning body."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.enums.definition_kind import DefinitionKind
    from domain_kernel.shared.domain.types.definition_reference import DefinitionReference
    from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference


@dataclass(frozen=True, kw_only=True)
class ShapeReference:
    """One typed edge plus its path within the owning body."""

    target: DefinitionReference
    expected_kind: DefinitionKind | None
    path: tuple[str | int, ...]
    closed_vocabulary: bool = False
    embedded: bool = False
    term: ModelTermReference | None = None
