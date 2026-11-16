"""Typed choices available for manual definition review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from domain_kernel._shared.domain.definitions import (
    ConceptDefinition,
    RelationshipDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
)
from domain_kernel._shared.domain.model_values import Terminology
from domain_kernel._shared.domain.naming import require_lookup_name
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.domain.definitions import DefinitionBody


@dataclass(frozen=True, kw_only=True)
class Accept:
    """Accept the effect captured in the inspected review case."""

    reason: str
    kind: Literal["accept"] = "accept"

    def __post_init__(self) -> None:
        """Preserve the explicit review action and reason."""
        require_text(value=self.reason, field="Decision reason")
        require_exact(value=self.kind, expected=str, field="Decision kind")
        if self.kind != "accept":
            raise ValueError("Use the accept decision kind")


@dataclass(frozen=True, kw_only=True)
class EditDefinition:
    """Accept edited content for the same proposed identity and lookup name."""

    definition_id: DefinitionId
    name: str
    display_name: str
    meaning: str
    body: DefinitionBody
    reason: str
    aliases: Sequence[str] = ()
    terminology: Terminology = field(default_factory=Terminology)
    kind: Literal["edit_definition"] = "edit_definition"

    def __post_init__(self) -> None:
        """Validate the proposed replacement content and freeze aliases."""
        require_text(value=self.reason, field="Decision reason")
        require_exact(value=self.kind, expected=str, field="Decision kind")
        if self.kind != "edit_definition":
            raise ValueError("Use the edit_definition decision kind")
        require_exact(value=self.definition_id, expected=DefinitionId, field="Definition identity")
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Display name")
        require_text(value=self.meaning, field="Definition meaning")
        require_exact(value=self.terminology, expected=Terminology, field="Terminology")
        if type(self.body) not in (
            ConceptDefinition,
            RelationshipDefinition,
            StructuredValueDefinition,
            UnitDefinition,
            ValueSetDefinition,
        ):
            raise TypeError("Supply a supported definition body")
        aliases = snapshot_sequence(items=self.aliases, item_type=str, field="Definition aliases")
        object.__setattr__(self, "aliases", aliases)


@dataclass(frozen=True, kw_only=True)
class Reject:
    """Resolve a case by declining its proposed effects."""

    reason: str
    kind: Literal["reject"] = "reject"

    def __post_init__(self) -> None:
        """Preserve the explicit review action and reason."""
        require_text(value=self.reason, field="Decision reason")
        require_exact(value=self.kind, expected=str, field="Decision kind")
        if self.kind != "reject":
            raise ValueError("Use the reject decision kind")


type ReviewAction = Accept | EditDefinition | Reject
