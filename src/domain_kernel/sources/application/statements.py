"""Capture and reopen the exact text of attributed statements."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.shared.hashing import Hashing
from domain_kernel.sources.application.parsed_sources import resolved_content
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.models import (
    Evidence,
    IngestedSource,
    ProcessingRecord,
    SourceRevision,
)
from domain_kernel.sources.domain.parsed import ParsedText, StatementSpan
from domain_kernel.sources.domain.statements import StatementOrigin, StatementPayload

if TYPE_CHECKING:
    from domain_kernel.sources.application.contracts import Statement
    from domain_kernel.sources.domain.models import EvidenceContent, ProcessingLimits, Source


def attributed_payload(*, statement: Statement, actor: str) -> StatementPayload:
    """Resolve attribution at ingestion with independent statement and capture times."""
    return StatementPayload(
        text=statement.text,
        origin=StatementOrigin(
            speaker=statement.speaker,
            recorded_by=actor if statement.recorded_by is None else statement.recorded_by,
            stated_at=statement.stated_at,
            recorded_at=datetime.now(tz=UTC),
            context=statement.context,
            form=statement.form,
            intent=statement.intent,
        ),
    )


def canonical_statement(*, payload: StatementPayload, limits: ProcessingLimits) -> bytes:
    """Hash statement meaning and attribution with no dependence on the capture clock."""
    origin = payload.origin
    fields = (
        payload.text,
        origin.context,
        origin.recorded_by,
        origin.speaker.name,
        origin.speaker.role,
        origin.speaker.id.value,
    )
    if sum(len(value) for value in fields) > limits.max_source_bytes:
        raise ResourceLimitError(message="Keep the statement within the configured source limit.")
    content = CanonicalJson.encode(
        value={
            "kind": origin.kind,
            "version": origin.payload_schema_version,
            "text": payload.text,
            "speaker": {
                "id": origin.speaker.id.value,
                "name": origin.speaker.name,
                "role": origin.speaker.role,
            },
            "stated_at": None
            if origin.stated_at is None
            else origin.stated_at.astimezone(UTC).isoformat(),
            "recorded_by": origin.recorded_by,
            "context": origin.context,
            "form": origin.form.value,
            "intent": origin.intent.value,
        },
    )
    if len(content) > limits.max_source_bytes:
        raise ResourceLimitError(message="Keep the statement within the configured source limit.")
    return content


def capture_statement(
    *,
    source: Source,
    payload: StatementPayload,
    canonical: bytes,
) -> IngestedSource:
    """Issue one exact citation for a statement without confirming its claim."""
    revision = SourceRevision(
        project_id=source.project_id,
        source_id=source.id,
        revision_id=SourceRevisionId(value=Hashing.hash_bytes(content=canonical).value),
        origin=payload.origin,
        byte_length=len(canonical),
    )
    locator = StatementSpan(start=0, end=len(payload.text))
    fingerprint = Hashing.hash_json(
        value=("attributed-statement", payload.origin.payload_schema_version)
    ).value
    evidence = Evidence(
        id=EvidenceId(
            value=Hashing.hash_json(
                value=(
                    revision.project_id.value,
                    revision.source_id.value,
                    revision.revision_id.value,
                    "statement",
                    locator.start,
                    locator.end,
                )
            ).value,
        ),
        source=revision,
        locator=locator,
        processing=ProcessingRecord(
            source=revision,
            fingerprint=fingerprint,
            parser_id="attributed-statement",
            parser_version=str(payload.origin.payload_schema_version),
        ),
    )
    return IngestedSource(
        revision=revision,
        processing_fingerprint=fingerprint,
        evidence=(evidence,),
    )


def resolve_statement(
    *,
    evidence: Evidence,
    payload: StatementPayload,
    limits: ProcessingLimits,
) -> EvidenceContent:
    """Verify the exact primary statement before resolving its cited span."""
    canonical = canonical_statement(payload=payload, limits=limits)
    if (
        evidence.source.origin != payload.origin
        or len(canonical) != evidence.source.byte_length
        or Hashing.hash_bytes(content=canonical).value != evidence.source.revision_id.value
    ):
        raise SourceRevisionMismatchError
    locator = evidence.locator
    if not isinstance(locator, StatementSpan) or locator.end > len(payload.text):
        raise EvidenceUnavailableError
    return resolved_content(
        evidence=evidence,
        part=ParsedText(text=payload.text[locator.start : locator.end], locator=locator),
    )
