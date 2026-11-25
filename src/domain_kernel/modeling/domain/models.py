"""Loaded metadata for one independent model workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.modeling.domain.enums.model_kind import ModelKind
from domain_kernel.shared.contracts import ModelScope, ModelVersion
from domain_kernel.shared.domain.naming import require_lookup_name
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.validation import require_exact, require_text, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class ReferencePackPin:
    """Identity and digest of one immutable approved reference pack."""

    key: str
    version: str
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Require an exact named version and hash."""
        require_text(value=self.key, field="Reference pack key")
        require_text(value=self.version, field="Reference pack version")
        require_exact(value=self.content_hash, expected=ContentHash, field="Reference pack hash")


@dataclass(frozen=True, kw_only=True)
class ModelInfo:
    """Detached workspace state at one observed revision."""

    scope: ModelScope
    name: str
    display_name: str
    kind: ModelKind
    description: str
    created_at: datetime
    revision: int
    reference_pack: ReferencePackPin | None = None
    baseline: ModelVersion | None = None
    dependencies: Sequence[ModelVersion] = ()

    def __post_init__(self) -> None:
        """Validate scope and authoring intent, retaining a fixed dependency snapshot."""
        require_exact(value=self.scope, expected=ModelScope, field="Model scope")
        require_lookup_name(name=self.name)
        require_text(value=self.display_name, field="Model display name")
        require_text(value=self.description, field="Model description")
        require_exact(value=self.kind, expected=ModelKind, field="Model kind")
        require_exact(value=self.revision, expected=int, field="Workspace revision")
        if self.revision < 0:
            raise ValueError("Workspace revision must be nonnegative")
        if self.created_at.utcoffset() is None:
            raise ValueError("Model creation time must include a time zone")
        if self.reference_pack is not None:
            require_exact(
                value=self.reference_pack, expected=ReferencePackPin, field="Reference pack"
            )
        if self.baseline is not None:
            require_exact(value=self.baseline, expected=ModelVersion, field="Model baseline")
        dependencies = snapshot_sequence(
            items=self.dependencies,
            item_type=ModelVersion,
            field="Model dependencies",
        )
        object.__setattr__(self, "dependencies", dependencies)
