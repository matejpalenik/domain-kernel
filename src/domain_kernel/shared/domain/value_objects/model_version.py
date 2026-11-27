from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.model_scope import ModelScope
from domain_kernel.shared.identifiers.content_hash import ContentHash


@dataclass(frozen=True, kw_only=True)
class ModelVersion:
    """Immutable version identity for a model snapshot."""

    scope: ModelScope
    version: str
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the exact scope, label, and content digest types."""
        if type(self.scope) is not ModelScope:
            raise TypeError("ModelVersion scope must be a ModelScope")

        if type(self.version) is not str:
            raise TypeError("ModelVersion version must be a string")
        if not self.version:
            raise ValueError("ModelVersion version must be a nonempty string")

        if type(self.content_hash) is not ContentHash:
            raise TypeError("ModelVersion content_hash must be a ContentHash")
