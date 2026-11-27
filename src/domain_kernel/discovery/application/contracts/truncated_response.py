from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class TruncatedResponse:
    """A returned provider receipt with an incomplete output."""

    fragment: str | None = field(repr=False)
    model_id: str
    provider_request_id: str | None
    provider_endpoint: str
    input_tokens: int | None
    output_tokens: int | None
