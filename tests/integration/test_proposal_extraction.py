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
    MissingCapabilityError,
    ModelKind,
    ModelRequest,
    ModelResponse,
    Person,
    PersonId,
    Statement,
    StatementForm,
    StatementIntent,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel import Model, SourceRevision

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_RESPONSE = (
    '{"concepts":[{"name":"application-code","display_name":"Application code",'
    '"meaning":"A lookup code for a reviewed provision.","citations":[1],"confidence":null}],'
    '"relationships":[]}'
)
_TEXT = "This code locates a provision in our recruitment application."


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


async def _workspace(
    *,
    path: Path,
    gateway: _Gateway | None,
) -> tuple[Model, SourceRevision]:
    project = await Client(
        config=ClientConfiguration(
            base_dir=path,
            model_gateway=gateway,
        )
    ).create_project(actor="editor", name="recruitment")
    statement = await project.ingest_source(
        actor="editor",
        name="application-code-interview",
        source=Statement(
            text=_TEXT,
            speaker=Person(id=PersonId(value="developer"), name="Ari", role="Developer"),
            context="Application codes",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    model = await project.create_model(
        actor="editor",
        name="locators",
        kind=ModelKind.PROPOSED,
        description="The application needs internal lookup codes.",
    )
    return model, statement.revision


class _Selection(TypedDict):
    actor: str
    idempotency_key: str
    additional_instructions: str
    prompt_override: str


async def test_extraction_uses_the_same_gateway_and_reopens_exact_draft(tmp_path: Path) -> None:
    gateway = _Gateway(failures=1)
    model, revision = await _workspace(path=tmp_path, gateway=gateway)
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
    assert _TEXT not in first.instructions
    assert first.inputs[0].text == _TEXT
    assert "internal lookup codes" in (first.context_json or "")
    (proposal,) = draft.proposals
    assert type(proposal.definition.body) is ConceptDefinition
    assert proposal.evidence[0].source == revision
    assert proposal.definition.status is DefinitionStatus.PROPOSED
    assert draft.provenance.provider_model_id == "stored/test-model"
    assert draft.provenance.input_tokens is not None

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
    model, revision = await _workspace(path=tmp_path, gateway=gateway)
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
    model, revision = await _workspace(path=tmp_path, gateway=None)
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
