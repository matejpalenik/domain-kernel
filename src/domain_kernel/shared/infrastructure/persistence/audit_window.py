"""Bind audit pagination to a query and fixed sequence window."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass

from domain_kernel.shared.application.results.page_cursor import PageCursor


@dataclass(frozen=True, kw_only=True)
class AuditWindow:
    """The stable sequence bounds of a paginated audit query."""

    last: int
    ceiling: int

    @classmethod
    def decode(cls, *, cursor: PageCursor, key: str) -> AuditWindow:
        """Recover the sequence bounds from a cursor bound to the same audit query."""
        try:
            parts = urlsafe_b64decode(cursor.value).decode("ascii").split(",")
            query, last, ceiling = parts
            if query == key and 0 < int(last) < int(ceiling):
                return cls(last=int(last), ceiling=int(ceiling))
        except ValueError:
            pass

        raise ValueError("Use a valid cursor from the same audit history query")

    def encode(self, *, key: str) -> PageCursor:
        """Bind this window to the query key in an opaque continuation cursor."""
        return PageCursor(
            value=urlsafe_b64encode(f"{key},{self.last},{self.ceiling}".encode("ascii")).decode(
                "ascii"
            ),
        )
