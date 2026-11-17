"""Exact reference-pack transitions and their review scope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.discovery.domain.identifiers.obligation_id import ObligationId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.reference_packs.domain.packs import ReferencePack
from domain_kernel.review.domain.identifiers.review_case_id import ReviewCaseId
from domain_kernel.shared.validation import require_exact, snapshot_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel.modeling.domain.models import ReferencePackPin
    from domain_kernel.reference_packs.domain.contracts import ReferencePackObligation


@dataclass(frozen=True, kw_only=True)
class ReferencePackChange:
    """The exact old and proposed selections with affected local review work."""

    before: ReferencePack | None
    after: ReferencePack | None
    added_obligation_ids: Sequence[ObligationId]
    removed_obligation_ids: Sequence[ObligationId]
    changed_obligation_ids: Sequence[ObligationId]
    affected_definition_ids: Sequence[DefinitionId]
    superseded_case_ids: Sequence[ReviewCaseId]

    def __post_init__(self) -> None:
        """Detach the inspected effects and preserve distinct exact identities."""
        for pack in (self.before, self.after):
            if pack is not None:
                require_exact(value=pack, expected=ReferencePack, field="Reference pack selection")
        if pack_pin(pack=self.before) == pack_pin(pack=self.after):
            raise ValueError("Select a different exact reference pack or remove the current pack.")
        for name, items, item_type in (
            ("added_obligation_ids", self.added_obligation_ids, ObligationId),
            ("removed_obligation_ids", self.removed_obligation_ids, ObligationId),
            ("changed_obligation_ids", self.changed_obligation_ids, ObligationId),
            ("affected_definition_ids", self.affected_definition_ids, DefinitionId),
            ("superseded_case_ids", self.superseded_case_ids, ReviewCaseId),
        ):
            captured = snapshot_sequence(items=items, item_type=item_type, field=name)
            if len(set(captured)) != len(captured):
                raise ValueError("Choose each affected identity once.")
            object.__setattr__(self, name, captured)


def pack_pin(*, pack: ReferencePack | None) -> ReferencePackPin | None:
    """Read the exact selected pin, preserving absence."""
    return None if pack is None else pack.pin


def _by_id(*, pack: ReferencePack | None) -> dict[ObligationId, ReferencePackObligation]:
    return {} if pack is None else {item.id: item for item in pack.obligations}


def describe_pack_change(
    *,
    before: ReferencePack | None,
    after: ReferencePack | None,
    definitions: Sequence[DefinitionId],
    superseded: Sequence[ReviewCaseId],
) -> ReferencePackChange:
    """Compare obligations by declared IDs across materialized versions."""
    old = _by_id(pack=before)
    new = _by_id(pack=after)
    return ReferencePackChange(
        before=before,
        after=after,
        added_obligation_ids=tuple(identity for identity in new if identity not in old),
        removed_obligation_ids=tuple(identity for identity in old if identity not in new),
        changed_obligation_ids=tuple(
            identity for identity in new if identity in old and old[identity] != new[identity]
        ),
        affected_definition_ids=definitions,
        superseded_case_ids=superseded,
    )
