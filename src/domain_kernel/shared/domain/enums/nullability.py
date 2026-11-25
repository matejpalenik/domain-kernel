"""Whether a present single-valued field may contain null."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class Nullability(StrEnum):
    """Whether a present single-valued field may contain null."""

    FORBIDDEN = "forbidden"
    ALLOWED = "allowed"
