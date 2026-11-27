from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain_kernel.discovery.application.protocols.model_gateway import ModelGateway


@dataclass(frozen=True, kw_only=True)
class ExtractionSettings:
    """Captured inference settings belonging to one host client."""

    gateway: ModelGateway
    timeout_seconds: float
    max_attempts: int
    max_input_bytes: int
    max_output_bytes: int
    max_proposals: int
    explicit_limits: frozenset[str] = frozenset()
