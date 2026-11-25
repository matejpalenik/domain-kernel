"""Build a deterministic, evidence-bearing request for SDK discovery tests."""

import json
from datetime import UTC, datetime
from hashlib import sha256

from domain_kernel import (
    Evidence,
    EvidenceId,
    ExternalLocation,
    InferenceInput,
    ModelRequest,
    ParsedSourceOrigin,
    ProcessingRecord,
    ProjectId,
    SourceId,
    SourceRevision,
    SourceRevisionId,
)
from domain_kernel.discovery.application.prompts import DEFAULT_INSTRUCTIONS
from domain_kernel.discovery.application.structured_output import response_schema


def make_request(*, name: str, text: str, scope: str, arm: str) -> ModelRequest:
    """Attach a distinct revision and exact citation to the supplied fixture text."""
    content = text.encode()
    revision = SourceRevision(
        project_id=ProjectId(value="test-project"),
        source_id=SourceId(value=name),
        revision_id=SourceRevisionId(value="sha256:" + sha256(content).hexdigest()),
        byte_length=len(content),
        origin=ParsedSourceOrigin(
            provider="fixture",
            document_id=name,
            document_revision="1",
            captured_at=datetime(2026, 11, 18, tzinfo=UTC),
        ),
    )
    evidence = Evidence(
        id=EvidenceId(value=name),
        source=revision,
        locator=ExternalLocation(key=name),
        processing=ProcessingRecord(
            source=revision, fingerprint="fixture-text-v1", parser_id="host", parser_version="1"
        ),
    )
    return ModelRequest(
        request_id=f"{arm}-{name.replace('.', '-')}",
        instructions=DEFAULT_INSTRUCTIONS,
        context_json=json.dumps({"description": scope, "approved_meanings": []}),
        response_schema_json=response_schema(),
        timeout_seconds=150.0,
        inputs=[InferenceInput(text=text, evidence=[evidence])],
    )
