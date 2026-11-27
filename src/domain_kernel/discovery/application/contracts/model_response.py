from __future__ import annotations

from dataclasses import dataclass, field

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.text_validation import TextValidation


@dataclass(frozen=True, kw_only=True)
class ModelResponse:
    """Provider output and usage detached from the transport."""

    output_json: str = field(repr=False)
    model_id: str
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_endpoint: str | None = None
    discovery_binding_json: str | None = field(default=None, repr=False)
    discovery_held_json: str | None = field(default=None, repr=False)
    discovery_coverage_json: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Verify metadata types while leaving response validation to the extractor."""
        TextValidation.require_text(value=self.output_json, field="Model output")
        TextValidation.require_text(value=self.model_id, field="Provider model")
        if self.discovery_binding_json is not None:
            TextValidation.require_text(
                value=self.discovery_binding_json, field="Discovery binding"
            )
        if self.discovery_held_json is not None:
            TextValidation.require_text(
                value=self.discovery_held_json, field="Held discovery relationships"
            )
        if self.discovery_coverage_json is not None:
            TextValidation.require_text(
                value=self.discovery_coverage_json, field="Discovery coverage"
            )
        for value in (self.provider_request_id, self.provider_endpoint):
            if value is not None:
                TextValidation.require_text(value=value, field="Provider metadata")

        for value in (self.input_tokens, self.output_tokens):
            if value is not None:
                RuntimeTypeValidation.require_exact(value=value, expected=int, field="Token usage")
                if value < 0:
                    raise ValueError("Use nonnegative provider usage")
