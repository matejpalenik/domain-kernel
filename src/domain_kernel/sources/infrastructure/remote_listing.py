"""Bind remote continuation tokens to an exact reader query."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import TYPE_CHECKING

from domain_kernel.shared.application.results.page_cursor import PageCursor
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.errors.stale_state_error import StaleStateError
from domain_kernel.shared.hashing import Hashing
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.configuration import SourceSelectionLimits
    from domain_kernel.sources.application.contracts import ReaderLocation


_MAX_TOKEN_LENGTH = 16_384
_MAX_CURSOR_LENGTH = 32_768


def listing_binding(
    *, scope: str, location: ReaderLocation, limits: SourceSelectionLimits, limit: int
) -> str:
    """Verify page size and seal the provider-independent selection."""
    RuntimeTypeValidation.require_exact(value=limit, expected=int, field="Listing page size")
    if not 1 <= limit <= min(1000, limits.max_listing_entries):
        raise ResourceLimitError(message="Request a bounded page of remote source entries.")
    return Hashing.hash_json(value=(scope, location.reader, location.path, limit)).value


def read_continuation(*, cursor: PageCursor | None, binding: str) -> str | None:
    """Open an opaque token only for the same root, location, and page size."""
    if cursor is None:
        return None
    RuntimeTypeValidation.require_exact(
        value=cursor, expected=PageCursor, field="Listing continuation"
    )
    if len(cursor.value) <= _MAX_CURSOR_LENGTH:
        try:
            captured, token = urlsafe_b64decode(cursor.value).decode("utf-8").split("\0", 1)
            if captured == binding and token and "\0" not in token:
                return token
        except ValueError:
            pass
    raise StaleStateError(message="Restart listing from the exact configured remote selection.")


def next_page(*, token: str | None, binding: str) -> PageCursor | None:
    """Encode a bounded provider continuation without granting any new scope."""
    if token is None:
        return None
    if not token or len(token) > _MAX_TOKEN_LENGTH or "\0" in token:
        raise ResourceLimitError(message="The provider returned an invalid continuation token.")
    return PageCursor(value=urlsafe_b64encode(f"{binding}\0{token}".encode()).decode())
