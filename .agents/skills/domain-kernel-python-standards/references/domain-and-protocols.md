# Domain behavior and protocol boundaries

Read this when choosing the owner of a transition, value or interface. The
[architecture](../../../../docs/architecture/components-and-ownership.md#internal-architecture) owns the dependency
rule. Read the owning Python module for exact signatures. The examples illustrate
internal implementation choices, not additional public APIs.

## Reject a duplicate before changing state

While authoring a model, a developer checks the draft's names locally. The index
rejects a second draft entry with the same name or identity. This creates no durable
catalogue reservation: authored names are reserved atomically on submission. The
self-contained `domain_example.py` is a fixture for the testing skill's exercise.
In production, define each type in its own module. Use `definition_name_index.py`,
`draft_definition_name.py` and `draft_name_conflict_error.py` for this layout. The
production catalogue also preserves approved and removed names and releases only
permitted reservations.

```python
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId


class DraftNameConflictError(ValueError):
    """The example index already contains this name or identity."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DraftDefinitionName:
    definition_id: DefinitionId
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.definition_id, DefinitionId):
            raise TypeError("definition_id must be a DefinitionId")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if re.fullmatch(pattern=r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", string=self.name) is None:
            raise ValueError("name must be a normalized lookup name")


class DefinitionNameIndex:
    """Own a draft's in-memory names without exposing collection mutation."""

    def __init__(self, *, entries: Sequence[DraftDefinitionName] = ()) -> None:
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
            raise TypeError("entries must be a sequence of DraftDefinitionName values")
        self._entries: tuple[DraftDefinitionName, ...] = ()
        for entry in entries:
            self.add(entry=entry)

    @property
    def entries(self) -> tuple[DraftDefinitionName, ...]:
        return self._entries

    def add(self, *, entry: DraftDefinitionName) -> None:
        if not isinstance(entry, DraftDefinitionName):
            raise TypeError("entry must be a DraftDefinitionName")
        if any(
            item.name == entry.name or item.definition_id == entry.definition_id
            for item in self._entries
        ):
            raise DraftNameConflictError("The name or identity is already present")
        self._entries = (*self._entries, entry)
```

The invariant is in the domain component, not a service's `if` branch. A failed add
leaves the existing tuple unchanged. An input list is never retained, and inspection
cannot mutate the owned collection. A database unique constraint is still necessary
for competing operations: this isolated index does not prove concurrency safety.
When integrating the behavior, use the SDK's owning typed conflict error rather than
exporting this example-specific exception.

Use this in-place pattern for editable entities. The index returns an immutable
view of its owned collection. Its `add()` returns `None` because the transition
produces no separate domain result. Definitions and publication snapshots remain
immutable values.

## Put protocols on the correct side

An application service implements its inbound application capability. It receives
repository, transaction and external-provider protocols declared by the consuming
application layer. Infrastructure implementations import those protocols, never the
reverse. Keep SQLAlchemy out of both the protocol signatures and domain types.

Use `@abstractmethod` for required authored methods and `@override` in implementations
and fakes. Runtime-checkable protocols are not input validators. Nominal IDs and
validated records protect values; protocols describe capabilities.

The dependency rule takes precedence over explicit inheritance. In particular,
DK-008's pure `ModelReadinessEvaluator` structurally satisfies its application port
without importing that port, even under `TYPE_CHECKING`. Verify that assignment in
application/composition typing checks; test the policy directly with captured values.

Do not add a protocol for `DraftDefinitionName`, every dataclass or every pure helper.
Use dedicated boundaries where substitution, lifecycle or ownership matters. Preserve
opaque identifier strings rather than imposing UUID storage; use explicit conversion
only in the owning codec or persistence mapper. Generated display-name slugs remain
the SDK's shared naming behavior, not a second implementation inside every service.
