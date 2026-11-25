"""Restore stored snapshot identities through their exact typed constructors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel.reference_packs.domain.contracts import Pattern
from domain_kernel.review.domain.decisions import MapToReference
from domain_kernel.shared.domain.data_shapes import AttributeDefinition, KeyDefinition
from domain_kernel.shared.domain.entities.activity import Activity
from domain_kernel.shared.domain.entities.condition import Condition
from domain_kernel.shared.domain.entities.event import Event
from domain_kernel.shared.domain.entities.flow import Flow
from domain_kernel.shared.domain.entities.gateway import Gateway
from domain_kernel.shared.domain.entities.role import Role

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_RESTORE_FIELDS: dict[str, Callable[..., object]] = {
    "Activity": Activity.restore,
    "Condition": Condition.restore,
    "Event": Event.restore,
    "Flow": Flow.restore,
    "Gateway": Gateway.restore,
    "Role": Role.restore,
    "MapToReference": MapToReference.restore,
    "Pattern": Pattern.restore,
    # Persistence validates the original nominal IDs through the same domain invariants.
    "AttributeDefinition": AttributeDefinition._from_snapshot,  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    "KeyDefinition": KeyDefinition._from_snapshot,  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
}


def construct_record(*, record: type[object], attributes: Mapping[str, object]) -> object:
    """Restore fields without generating replacements for persisted identities."""
    construct = _RESTORE_FIELDS.get(record.__name__, record)
    return construct(**attributes)
