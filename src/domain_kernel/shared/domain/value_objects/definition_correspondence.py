"""Exact pre-change and post-change definition identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId


@dataclass(frozen=True, kw_only=True)
class DefinitionCorrespondence:
    """Exact pre-change and post-change definition identities."""

    before_id: DefinitionId
    after_id: DefinitionId
