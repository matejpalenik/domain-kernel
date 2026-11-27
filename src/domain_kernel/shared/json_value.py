"""Define the recursive value shape accepted by canonical JSON encoding."""

from __future__ import annotations

from collections.abc import Sequence

type JsonValue = bool | int | float | str | Sequence[JsonValue] | dict[str, JsonValue] | None
