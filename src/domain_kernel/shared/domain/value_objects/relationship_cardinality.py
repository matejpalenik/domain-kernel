"""Directional participation bounds for a binary relationship."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.domain.value_objects.cardinality_bounds import CardinalityBounds
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation


@dataclass(frozen=True, kw_only=True)
class RelationshipCardinality:
    """Directional participation bounds for a binary relationship."""

    outgoing: CardinalityBounds
    incoming: CardinalityBounds

    def __post_init__(self) -> None:
        """Require a distinct participation contract for each direction."""
        RuntimeTypeValidation.require_exact(
            value=self.outgoing, expected=CardinalityBounds, field="Outgoing cardinality"
        )
        RuntimeTypeValidation.require_exact(
            value=self.incoming, expected=CardinalityBounds, field="Incoming cardinality"
        )

    @classmethod
    def one_to_one(cls) -> RelationshipCardinality:
        """Allow zero or one relationship in each direction."""
        return cls(outgoing=CardinalityBounds(), incoming=CardinalityBounds())

    @classmethod
    def one_to_many(cls) -> RelationshipCardinality:
        """Allow unbounded outgoing relationships and at most one incoming."""
        return cls(outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds())

    @classmethod
    def many_to_one(cls) -> RelationshipCardinality:
        """Allow at most one outgoing relationship and unbounded incoming."""
        return cls(outgoing=CardinalityBounds(), incoming=CardinalityBounds(maximum=None))

    @classmethod
    def many_to_many(cls) -> RelationshipCardinality:
        """Allow unbounded relationships in each direction."""
        return cls(
            outgoing=CardinalityBounds(maximum=None), incoming=CardinalityBounds(maximum=None)
        )
