"""Exercise extraction, guarded replay and failure recovery with a detached gateway."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, final

import pytest

from domain_kernel import (
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DefinitionStatus,
    IdempotencyConflictError,
    InferenceError,
    LocalReplayGateway,
    MissingCapabilityError,
    ModelRequest,
    ModelResponse,
)
from tests.support.discovery.create_discovery_workspace import (
    DISCOVERY_STATEMENT,
    create_discovery_workspace,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


_RESPONSE = (
    '{"concepts":[{"name":"application-code","display_name":"Application code",'
    '"meaning":"A lookup code for a reviewed provision.","citations":[1],"confidence":null}],'
    '"relationships":[]}'
)


@final
class _Gateway:
    def __init__(self, *, result: str = _RESPONSE, failures: int = 0) -> None:
        self.result = result
        self.failures = failures
        self.requests: list[ModelRequest] = []

    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) <= self.failures:
            raise InferenceError(retryable=True)
        return ModelResponse(
            output_json=self.result,
            model_id="stored/test-model",
            input_tokens=16,
            output_tokens=24,
        )


class _Selection(TypedDict):
    actor: str
    idempotency_key: str
    additional_instructions: str
    prompt_override: str


async def test_extraction_uses_the_same_gateway_and_reopens_exact_draft(tmp_path: Path) -> None:
    gateway = _Gateway(failures=1)
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=gateway)
    arguments: _Selection = {
        "actor": "editor",
        "idempotency_key": "first-extraction",
        "additional_instructions": "Include the lookup code.",
        "prompt_override": "Draft application-owned meanings.",
    }
    draft = await model.extract_proposals(source_revisions=[revision], **arguments)
    first, retried = gateway.requests
    assert retried == first
    assert first.instructions == "Draft application-owned meanings."
    assert DISCOVERY_STATEMENT not in first.instructions
    assert first.inputs[0].text == DISCOVERY_STATEMENT
    assert "internal lookup codes" in (first.context_json or "")
    (proposal,) = draft.proposals
    assert type(proposal.definition.body) is ConceptDefinition
    assert proposal.evidence[0].source == revision
    assert proposal.definition.status is DefinitionStatus.PROPOSED
    assert draft.provenance.provider_model_id == "stored/test-model"
    assert draft.provenance.input_tokens is not None
    assert not (await model.list_review_cases()).items
    assert not (await model.list_discovery_runs()).items

    reopened = await Client(
        config=ClientConfiguration(
            base_dir=tmp_path,
            model_gateway=gateway,
        )
    ).get_project(name="recruitment")
    again = await reopened.get_model(name="locators")
    assert await again.extract_proposals(source_revisions=[revision], **arguments) == draft
    assert gateway.requests == [first, retried]
    with pytest.raises(IdempotencyConflictError):
        _ = await again.extract_proposals(
            source_revisions=[revision],
            actor="editor",
            idempotency_key="first-extraction",
            prompt_override="Draft application-owned meanings.",
            additional_instructions="Changed even though the override wins.",
        )
    with pytest.raises(ValueError, match="nonblank"):
        _ = await again.extract_proposals(
            source_revisions=[revision],
            actor="editor",
            prompt_override=" ",
        )
    assert gateway.requests == [first, retried]


@pytest.mark.parametrize(
    "output",
    [
        '{"concepts":',
        _RESPONSE.replace('"citations":[1]', '"citations":[]'),
        _RESPONSE.replace('"citations":[1]', '"citations":[2]'),
        _RESPONSE.replace('"confidence":null', '"confidence":null,"approved":true'),
    ],
)
async def test_malformed_responses_do_not_become_drafts(tmp_path: Path, output: str) -> None:
    gateway = _Gateway(result=output)
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=gateway)
    with pytest.raises(InferenceError, match="Review provider output"):
        _ = await model.extract_proposals(
            actor="editor",
            source_revisions=[revision],
            idempotency_key="recover",
        )
    assert len(gateway.requests) == 1
    gateway.result = _RESPONSE
    recovered = await model.extract_proposals(
        actor="editor",
        source_revisions=[revision],
        idempotency_key="recover",
    )
    assert len(recovered.proposals) == 1


async def test_a_configured_gateway_is_required_only_for_extraction(tmp_path: Path) -> None:
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=None)
    with pytest.raises(MissingCapabilityError, match="model gateway"):
        _ = await model.extract_proposals(actor="editor", source_revisions=[revision])
    case = await model.propose_definition(
        actor="editor",
        name="manual-code",
        meaning="An authored code.",
        body=ConceptDefinition(),
        reason="Review independently.",
    )
    assert case.definitions


@pytest.mark.parametrize(
    ("output", "code", "path"),
    [
        (_RESPONSE.replace("[1]", "[2]"), "invalid_citation", ("concepts", 0, "citations", 0)),
        (
            _RESPONSE.replace("null", '"secret-value"'),
            "invalid_confidence",
            ("concepts", 0, "confidence"),
        ),
        (_RESPONSE.replace('"name":', '"name2":'), "invalid_shape", ("concepts", 0, "name")),
        (
            _RESPONSE.replace(
                '"relationships":[]',
                '"relationships":[{"name":"links","source":"application-code","target":"secret-value","display_name":"Link","meaning":"Link","citations":[1],"confidence":null}]',
            ),
            "unknown_endpoint",
            ("relationships", 0, "target"),
        ),
    ],
)
async def test_standalone_extraction_reports_the_invalid_field(
    tmp_path: Path, output: str, code: str, path: tuple[str | int, ...]
) -> None:
    model, revision = await create_discovery_workspace(
        path=tmp_path, gateway=_Gateway(result=output)
    )
    with pytest.raises(InferenceError) as caught:
        _ = await model.extract_proposals(source_revisions=[revision], actor="reviewer")
    issue = caught.value.issue
    assert issue is not None
    assert issue.path[-len(path) :] == path
    assert issue.code == code
    assert "secret-value" not in issue.message


async def test_raw_response_replay_preserves_the_failed_field_without_inference(
    tmp_path: Path,
) -> None:

    provider = _Gateway(result=_RESPONSE.replace("[1]", "[9]"))
    path = tmp_path / "private" / "responses.sqlite3"
    recorder = LocalReplayGateway(path=path, profile="test-model-1", gateway=provider)
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=recorder)
    with pytest.raises(InferenceError) as caught:
        _ = await model.extract_proposals(source_revisions=[revision], actor="reader")
    assert caught.value.issue is not None
    assert caught.value.issue.code == "invalid_citation"
    offline = LocalReplayGateway(path=path, profile="test-model-1")
    response = await offline.generate(request=provider.requests[0])
    assert response.output_json == provider.result
    assert path.stat().st_mode & 0o077 == 0
    assert len(provider.requests) == 1


async def test_journal_does_not_redispatch_an_uncertain_or_unretained_call(tmp_path: Path) -> None:
    broken = _Gateway(failures=1)
    path = tmp_path / "receipt.db"
    journal = LocalReplayGateway(path=path, profile="test", gateway=broken)
    model, revision = await create_discovery_workspace(path=tmp_path, gateway=journal)
    with pytest.raises(InferenceError, match="unresolved"):
        _ = await model.extract_proposals(source_revisions=[revision], actor="reader")
    assert len(broken.requests) == 1
    request = broken.requests[0]
    redacted = LocalReplayGateway(
        path=path, profile="digest-only", gateway=broken, retain_responses=False
    )
    _ = await redacted.generate(request=request)
    with pytest.raises(InferenceError, match="fingerprint"):
        _ = await LocalReplayGateway(path=path, profile="digest-only").generate(request=request)
    assert _RESPONSE.encode() not in path.read_bytes()
