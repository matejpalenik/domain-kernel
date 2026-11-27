"""Bind and restore shared review repository pagination."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING, final

from domain_kernel.shared.application.results.page import Page
from domain_kernel.shared.application.results.page_cursor import PageCursor
from domain_kernel.shared.hashing import Hashing

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from domain_kernel.shared.domain.value_objects.model_scope import ModelScope


@final
class ReviewPagination:
    """Encode cursors and restore pages for definition and review queries."""

    @staticmethod
    def key(*, scope: ModelScope, query: Sequence[str | None]) -> str:
        """Bind a continuation cursor to the exact model scope and query."""
        return Hashing.hash_json(value=[scope.project_id.value, scope.model_id.value, *query]).value

    @staticmethod
    def after(*, cursor: PageCursor | None, key: str, limit: int) -> str:
        """Validate the page request and return its previous position."""
        if type(limit) is not int or limit < 1:
            raise ValueError("Page limit must be a positive integer")
        if cursor is None:
            return ""
        try:
            saved_key, offset = (
                urlsafe_b64decode(cursor.value).decode("utf-8").split(",", maxsplit=1)
            )
            if key == saved_key:
                return offset
        except ValueError:
            pass
        raise ValueError("Use a cursor returned by the same query")

    @staticmethod
    def page[T](
        *,
        rows: Sequence[tuple[str, bytes]],
        key: str,
        limit: int,
        restore: Callable[[bytes], T],
    ) -> Page[T]:
        """Restore one page and encode a continuation when another row is available."""
        selected = rows[:limit]
        continuation = None
        if len(rows) > limit:
            value = urlsafe_b64encode(f"{key},{selected[-1][0]}".encode()).decode("ascii")
            continuation = PageCursor(value=value)
        return Page(items=tuple(restore(value) for _, value in selected), next_cursor=continuation)
