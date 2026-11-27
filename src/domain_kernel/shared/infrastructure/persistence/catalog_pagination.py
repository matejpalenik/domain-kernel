"""Scope stable name cursors to a project or model catalog query."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING, final

from domain_kernel.modeling.domain.models import ModelInfo
from domain_kernel.projects.domain.project_info import ProjectInfo
from domain_kernel.shared.application.results.page import Page
from domain_kernel.shared.application.results.page_cursor import PageCursor
from domain_kernel.shared.domain.policies.lookup_naming_policy import LookupNamingPolicy

if TYPE_CHECKING:
    from collections.abc import Sequence


@final
class CatalogPagination:
    """Read and write stable pagination cursors for catalogs."""

    @staticmethod
    def after_name(*, scope: str, cursor: PageCursor | None, limit: int) -> str:
        """Validate the page size and return the previous lookup name for this scope."""
        if type(limit) is not int or limit < 1:
            raise ValueError("Catalog page limit must be a positive integer")

        if cursor is None:
            return ""

        try:
            binding, name = urlsafe_b64decode(cursor.value).decode("ascii").split(",")
            if binding == scope:
                LookupNamingPolicy.require_lookup_name(name=name)
                return name
        except ValueError:
            pass

        raise ValueError("Use a cursor returned by the same catalog query")

    @staticmethod
    def page[T: ProjectInfo | ModelInfo](*, items: Sequence[T], scope: str, limit: int) -> Page[T]:
        """Return a page with a scoped continuation when the query found an extra row."""
        selected = items[:limit]
        cursor = None
        if len(items) > limit:
            token = urlsafe_b64encode(f"{scope},{selected[-1].name}".encode("ascii")).decode(
                "ascii"
            )
            cursor = PageCursor(value=token)

        return Page(items=selected, next_cursor=cursor)
