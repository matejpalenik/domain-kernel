"""Ways a descriptive process can branch or rejoin."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class GatewayKind(StrEnum):
    """How the described process branches or rejoins."""

    EXCLUSIVE = "exclusive"
    PARALLEL = "parallel"
