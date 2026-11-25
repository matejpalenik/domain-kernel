"""Check Codex transport contracts without spending account usage."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from sys import executable

import pytest

from benchmarks.procurement import (
    MeteredLuna,
    _costed,  # pyright: ignore[reportPrivateUsage] -- Check the run report.
)
from benchmarks.procurement_codex import CodexProcurementGateway
from benchmarks.procurement_run import ATTEMPTS
from benchmarks.procurement_score import Blind, Outcome, digest
from domain_kernel import (
    Evidence,
    EvidenceId,
    ExternalLocation,
    InferenceError,
    InferenceInput,
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


def _request() -> ModelRequest:
    revision = SourceRevision(
        project_id=ProjectId(value="project"),
        source_id=SourceId(value="source"),
        revision_id=SourceRevisionId(value=hash_bytes(content=b"notice").value),
        byte_length=6,
        origin=ParsedSourceOrigin(
            provider="host",
            document_id="test",
            document_revision="1",
            captured_at=datetime(2026, 11, 17, tzinfo=UTC),
        ),
    )
    evidence = Evidence(
        id=EvidenceId(value="evidence"),
        source=revision,
        locator=ExternalLocation(key="source-data"),
        processing=ProcessingRecord(
            source=revision, fingerprint="capture", parser_id="host", parser_version="1"
        ),
    )
    return ModelRequest(
        instructions="Inspect verified procurement evidence.",
        inputs=(InferenceInput(text="A lot can close without award.", evidence=(evidence,)),),
        context_json='{"scope":"Lots"}',
        response_schema_json="""{
            "type":"object","properties":{"answer":{"type":"boolean"}},
            "required":["answer"],"additionalProperties":false
        }""",
        request_id="request",
        timeout_seconds=5.0,
    )


def _fake(*, path: Path, body: str) -> CodexProcurementGateway:
    _ = path.write_text(f"#!{executable}\n{body}", encoding="utf-8")
    path.chmod(0o700)
    return CodexProcurementGateway(executable=str(path))


def _reported_retries(*, gateway: MeteredLuna) -> int:
    blind = Blind(id="retry-report")
    outcome = Outcome(
        packet="run",
        arm="open",
        complete=True,
        status="needs_review",
        blind=blind,
        local_sha256=digest(blind=blind),
        latency_seconds=1.0,
    )
    return _costed(outcome=outcome, calls=gateway.calls, backend="codex").retries


@pytest.mark.asyncio
async def test_successful_batches_with_one_stage_id_are_not_retries(tmp_path: Path) -> None:
    provider = MeteredLuna(
        provider=_fake(
            path=tmp_path / "fake-codex",
            body="""import sys
sys.stdin.read()
print('{"type":"item.completed","item":{"type":"agent_message","text":"{}"}}')
print('{"type":"turn.completed"}')
""",
        )
    )
    request = _request()
    _ = await provider.generate(request=request)
    _ = await provider.generate(request=replace(request, context_json='{"scope":"Awards"}'))
    assert _reported_retries(gateway=provider) == 0


@pytest.mark.asyncio
async def test_chatgpt_codex_returns_structured_output_and_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "fake-api-key")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    provider = _fake(
        path=tmp_path / "fake-codex",
        body="""import json
import os
import sys
from pathlib import Path
args = sys.argv[1:]
assert args[0] == "exec"
assert args[args.index("--model")+1] == "gpt-6-luna"
assert 'model_reasoning_effort="xhigh"' in args
assert 'forced_login_method="chatgpt"' in args
assert "--ephemeral" in args and "read-only" in args
assert "CODEX_API_KEY" not in os.environ and "OPENAI_API_KEY" not in os.environ
schema = Path(args[args.index("--output-schema")+1]).read_text()
assert json.loads(schema)["required"] == ["answer"]
data = json.load(sys.stdin)
assert data["interpretation_context"]["scope"] == "Lots"
assert data["verified_source_material"][0]["text"] == "A lot can close without award."
assert data["verified_source_material"][0]["citations"][0]["citation"] == 1
print('{"type":"thread.started","thread_id":"fixture-thread"}')
print('{"type":"turn.started"}')
print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"{\\"answer\\":true}"}}))
print('{"type":"turn.completed","usage":{"input_tokens":200,"output_tokens":9}}')
""",
    )
    result = await provider.generate(request=_request())
    assert result.output_json == '{"answer":true}'
    assert result.model_id == "codex/gpt-6-luna"
    assert (result.input_tokens, result.output_tokens) == (200, 9)
    assert result.provider_request_id == "fixture-thread"


@pytest.mark.asyncio
async def test_sdk_owns_three_retries_for_codex_dispatch(tmp_path: Path) -> None:
    count = tmp_path / "attempts"
    provider = _fake(
        path=tmp_path / "fake-codex",
        body=f"""import sys
from pathlib import Path
sys.stdin.read()
count = Path({str(count)!r})
attempt = int(count.read_text()) + 1 if count.exists() else 1
count.write_text(str(attempt))
if attempt < {ATTEMPTS}:
    print('{{"type":"turn.failed","error":{{"message":"server returned 503"}}}}')
    sys.exit(1)
print('{{"type":"item.completed","item":{{"type":"agent_message","text":"{{}}"}}}}')
print('{{"type":"turn.completed"}}')
""",
    )
    metered = MeteredLuna(provider=provider)
    journal = LocalReplayGateway(
        gateway=metered, path=tmp_path / "receipts.db", profile="codex-test", max_attempts=ATTEMPTS
    )
    request = _request()
    output = await journal.generate(request=request)
    assert output.output_json == "{}"
    assert int(count.read_text()) == ATTEMPTS
    assert await journal.generate(request=request) == output
    assert int(count.read_text()) == ATTEMPTS
    assert _reported_retries(gateway=metered) == ATTEMPTS - 1


@pytest.mark.asyncio
async def test_codex_rejects_tool_output_and_never_accepts_it_as_model_evidence(
    tmp_path: Path,
) -> None:
    provider = _fake(
        path=tmp_path / "fake-codex",
        body="""import sys
sys.stdin.read()
print('{"type":"item.started","item":{"type":"command_execution"}}')
print('{"type":"item.completed","item":{"type":"agent_message","text":"{}"}}')
print('{"type":"turn.completed"}')
""",
    )
    with pytest.raises(InferenceError, match="tool action") as failure:
        _ = await provider.generate(request=_request())
    assert not failure.value.retryable
