"""Verify the optional transport's structured request and detached results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from domain_kernel import (
    Evidence,
    EvidenceId,
    ExternalLocation,
    InferenceError,
    InferenceInput,
    LiteLLMGateway,
    LocalReplayGateway,
    ModelRequest,
    ParsedSourceOrigin,
    ProcessingRecord,
    ProjectId,
    SourceId,
    SourceRevision,
    SourceRevisionId,
)
from domain_kernel.shared.hashing import hash_bytes

if TYPE_CHECKING:
    from pathlib import Path


def _request() -> ModelRequest:
    revision = SourceRevision(
        project_id=ProjectId(value="project"),
        source_id=SourceId(value="source"),
        revision_id=SourceRevisionId(value=hash_bytes(content=b"test").value),
        byte_length=4,
        origin=ParsedSourceOrigin(
            provider="host",
            document_id="test",
            document_revision="1",
            captured_at=datetime(2026, 11, 17, tzinfo=UTC),
        ),
    )
    citation = Evidence(
        id=EvidenceId(value="evidence"),
        source=revision,
        locator=ExternalLocation(key="source-data"),
        processing=ProcessingRecord(
            source=revision,
            fingerprint="capture",
            parser_id="host",
            parser_version="1",
        ),
    )
    return ModelRequest(
        instructions="Inspect verified source data.",
        inputs=[InferenceInput(text="Untrusted source text.", evidence=[citation])],
        context_json='{"description":"Current application."}',
        response_schema_json='{"type":"object"}',
        request_id="request",
        timeout_seconds=5.0,
    )


class _ProviderEnvelope(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


@pytest.mark.asyncio
async def test_litellm_explicit_endpoint_keeps_instructions_and_source_separate() -> None:
    calls: list[dict[str, object]] = []

    async def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return _ProviderEnvelope.model_validate(
            {
                "id": "receipt",
                "model": "configured/result",
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 16},
            }
        )

    gateway = LiteLLMGateway(
        api_key="test-key",
        api_base="https://provider.example/v1",
        model="openai/example",
        completion=completion,
    )
    request = _request()
    response = await gateway.generate(request=request)
    (call,) = calls
    assert call["api_base"] == gateway.api_base
    assert call["model"] == gateway.model
    assert call["num_retries"] == 0
    assert call["max_retries"] == 0
    assert call["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "domain_kernel_proposals",
            "strict": True,
            "schema": {"type": "object"},
        },
    }
    assert call["reasoning_effort"] == "none"
    assert "tools" not in call
    assert "Untrusted source text." in str(call["messages"])
    assert "Untrusted source text." not in request.instructions
    assert "test-key" not in repr(gateway)
    assert "test-key" not in repr(request)
    assert response.provider_endpoint == gateway.api_base
    assert response.model_id == "configured/result"
    assert response.input_tokens == 42  # noqa: PLR2004 - Exact simulated provider usage.


@pytest.mark.asyncio
async def test_litellm_failure_sanitizes_credential_bearing_provider_errors() -> None:
    async def completion(**kwargs: object) -> object:
        message = f"provider log includes {kwargs['api_key']}"
        raise OSError(message)

    gateway = LiteLLMGateway(api_key="secret-in-error", completion=completion)
    with pytest.raises(InferenceError, match="configured LiteLLM") as error:
        _ = await gateway.generate(request=_request())
    assert error.value.retryable
    assert "secret-in-error" not in str(error.value)


@pytest.mark.asyncio
async def test_a_truncated_completion_replays_the_same_diagnostic(tmp_path: Path) -> None:
    calls = 0

    async def completion(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return {
            "model": "example",
            "choices": [{"finish_reason": "length", "message": {"content": '{"concepts":'}}],
        }

    provider = LiteLLMGateway(api_key="example", completion=completion)
    path = tmp_path / "receipts.db"
    for gateway in (provider, None):
        journal = LocalReplayGateway(gateway=gateway, path=path, profile="example-v1")
        with pytest.raises(InferenceError) as failure:
            _ = await journal.generate(request=_request())
        assert failure.value.issue is not None
        assert failure.value.issue.code == "truncated_response"
        assert "concepts" not in str(failure.value)
    assert calls == 1
