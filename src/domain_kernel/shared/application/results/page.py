from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain_kernel.shared.application.results.page_cursor import PageCursor
from domain_kernel.shared.validators.sequence_validation import SequenceValidation

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, init=False)
class Page[T]:
    """Immutable page of results and its continuation.

    Attributes:
        items: Results from this page in query order.
        next_cursor: Opaque cursor for the same query, or None on the last page.
    """

    items: tuple[T, ...]
    next_cursor: PageCursor | None

    def __init__(self, *, items: Sequence[T], next_cursor: PageCursor | None = None) -> None:
        """Snapshot input items and validate the optional cursor."""
        if not SequenceValidation.is_non_string_sequence(value=items):
            raise TypeError("Page items must be a sequence such as a list or tuple")

        if next_cursor is not None and type(next_cursor) is not PageCursor:
            raise TypeError("Page next_cursor must be a PageCursor or None")

        object.__setattr__(self, "items", tuple(items))
        object.__setattr__(self, "next_cursor", next_cursor)
