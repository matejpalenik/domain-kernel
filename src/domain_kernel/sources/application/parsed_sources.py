"""Capture and resolve exact evidence from caller-owned normalized payloads."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from domain_kernel._shared.domain.record_encoding import record_value
from domain_kernel.shared.hashing import canonical_json_bytes, hash_bytes, hash_json
from domain_kernel.shared.validation import require_exact
from domain_kernel.sources.domain.errors.evidence_unavailable_error import EvidenceUnavailableError
from domain_kernel.sources.domain.errors.source_revision_mismatch_error import (
    SourceRevisionMismatchError,
)
from domain_kernel.sources.domain.identifiers.evidence_id import EvidenceId
from domain_kernel.sources.domain.identifiers.source_revision_id import SourceRevisionId
from domain_kernel.sources.domain.models import (
    Evidence,
    EvidenceContent,
    IngestedSource,
    ProcessingRecord,
    SourceRevision,
)
from domain_kernel.sources.domain.parsed import ParsedPayload, ParsedTable, ParsedText
from domain_kernel.sources.domain.parsed_codec import canonical_capture, part_value

if TYPE_CHECKING:
    from domain_kernel.sources.domain.models import ProcessingLimits, Source
    from domain_kernel.sources.domain.parsed import EvidenceLocator, ParsedPart


def _part_locators(*, part: ParsedPart) -> tuple[EvidenceLocator, ...]:
    return (part.locator, *part.row_locators) if isinstance(part, ParsedTable) else (part.locator,)


def capture_host_payload(
    *,
    source: Source,
    payload: ParsedPayload,
    canonical: bytes,
) -> IngestedSource:
    """Create the exact immutable revision and citations for the provided capture."""
    digest = hash_bytes(content=canonical)
    revision = SourceRevision(
        project_id=source.project_id,
        source_id=source.id,
        revision_id=SourceRevisionId(digest.value),
        byte_length=len(canonical),
        origin=payload.origin,
    )
    processing = ProcessingRecord(
        source=revision,
        fingerprint=hash_json(
            value=("host-supplied", payload.schema_version, payload.origin.provider),
        ).value,
        parser_id="host-supplied",
        parser_version=str(payload.schema_version),
    )
    evidence = tuple(
        Evidence(
            id=EvidenceId(
                hash_json(
                    value=record_value(
                        value=(source.project_id, source.id, revision.revision_id, locator),
                    )
                ).value
            ),
            source=revision,
            locator=locator,
            processing=processing,
        )
        for item in payload.parts
        for locator in _part_locators(part=item)
    )
    return IngestedSource(
        revision=revision,
        processing_fingerprint=processing.fingerprint,
        evidence=evidence,
    )


def _at_locator(*, payload: ParsedPayload, locator: EvidenceLocator) -> ParsedPart:
    for part in payload.parts:
        if part.locator == locator:
            return part
        if isinstance(part, ParsedTable) and locator in part.row_locators:
            index = part.row_locators.index(locator)
            return replace(part, rows=(part.rows[index],), locator=locator, row_locators=())
    raise EvidenceUnavailableError


def resolve_host_content(
    *,
    evidence: Evidence,
    payload: ParsedPayload,
    limits: ProcessingLimits,
) -> EvidenceContent:
    """Verify every part before exposing the exact requested content."""
    require_exact(value=payload, expected=ParsedPayload, field="Resolved host capture")
    canonical = canonical_capture(payload=payload, limits=limits)
    revision = evidence.source
    if len(canonical) != revision.byte_length or (
        hash_bytes(content=canonical).value != revision.revision_id.value
    ):
        raise SourceRevisionMismatchError
    part = _at_locator(payload=payload, locator=evidence.locator)
    excerpt = (
        part.text
        if isinstance(part, ParsedText)
        else canonical_json_bytes(value=part_value(part=part)).decode()
    )
    return EvidenceContent(evidence=evidence, excerpt=excerpt, origin=revision.origin, part=part)
