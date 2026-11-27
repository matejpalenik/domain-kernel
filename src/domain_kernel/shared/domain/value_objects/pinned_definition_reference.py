from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion


@dataclass(frozen=True, kw_only=True)
class PinnedDefinitionReference:
    """Definition identity pinned to one exact immutable model version."""

    model: ModelVersion
    definition_id: DefinitionId
    definition_revision: int
    kind: Literal["pinned_definition"] = "pinned_definition"

    def __post_init__(self) -> None:
        """Enforce exact types, positive revision, and fixed discriminator."""
        if type(self.model) is not ModelVersion:
            raise TypeError("PinnedDefinitionReference model must be a ModelVersion")
        if type(self.definition_id) is not DefinitionId:
            raise TypeError("PinnedDefinitionReference definition_id must be a DefinitionId")

        if type(self.definition_revision) is not int:
            raise TypeError("PinnedDefinitionReference revision must be an exact integer")
        if self.definition_revision < 1:
            raise ValueError("PinnedDefinitionReference revision must be a positive exact integer")

        if type(self.kind) is not str:
            raise TypeError("PinnedDefinitionReference kind must be a string")
        if self.kind != "pinned_definition":
            raise ValueError("PinnedDefinitionReference kind must be 'pinned_definition'")
