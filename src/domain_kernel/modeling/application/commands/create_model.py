"""Capture the caller's intent to create a model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.enums.model_kind import ModelKind
    from domain_kernel.modeling.domain.snapshots import DomainModelBundle
    from domain_kernel.reference_packs.api.packs import ReferencePack
    from domain_kernel.shared.domain.value_objects.model_version import ModelVersion


@dataclass(frozen=True, kw_only=True)
class CreateModel:
    """The inputs for one model creation request."""

    actor: str
    kind: ModelKind
    description: str
    display_name: str | None
    name: str | None
    reference_pack: ReferencePack | None = None
    copy_from: DomainModelBundle | None = None
    dependencies: Sequence[ModelVersion] = ()
