"""Replay a labelled discovery transcript through the SDK's actual extractor."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, final, override

from pydantic import BaseModel

from domain_kernel import (
    ContentHash,
    DocumentSpan,
    ExternalLocation,
    ModelGateway,
    ModelResponse,
    ParsedPayload,
    ParsedSourceOrigin,
    ParsedSourceProvider,
    ParsedText,
    SourceUnavailableError,
)
from domain_kernel.shared.hashing import canonical_json_bytes
from examples.notebooks._preview.catalogue import load_sources

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from domain_kernel import ModelRequest, ProcessingLimits
    from domain_kernel.shared.hashing import JsonValue


_FOLDER = Path(__file__).parent / "fixtures"
_PROVIDED_DIGEST = "bba630444b3278e881066774002a1d7824308934f49ccfa203e65be43692f55e"
_PROVIDER = "tour-discovery-replay"
_GUIDANCE_PROVIDER = "tour-guidance-replay"
RECRUITMENT_FOCUS = (
    "Focus on recruitment systems, recruitment actors and safeguards. "
    "Preserve qualifications and supporting definitions wherever they appear."
)
DOCUMENTATION_OVERRIDE = "Draft only the instructions-for-use meaning and cite its source."
GUIDANCE_FOCUS = "Record how the Commission groups the elements of the AI-system definition."


class _Meaning(BaseModel):
    name: str
    display_name: str
    meaning: str
    page: int
    passage: str

    def response(self, *, indexes: dict[int | str, int]) -> dict[str, JsonValue]:
        citation = indexes.get(self.page) or indexes[self.passage]
        return {
            "name": self.name,
            "display_name": self.display_name,
            "meaning": self.meaning,
            "citations": [citation],
            "confidence": None,
        }


class _Relationship(_Meaning):
    source: str
    target: str


class _UpdateExpectations(BaseModel):
    source: str
    sha256: str
    edition: str
    concept: _Meaning


def _guidance_expectations() -> _UpdateExpectations:
    return _UpdateExpectations.model_validate_json(
        (_FOLDER / "discovery-update-expectations.json").read_bytes(),
    )


class _ReplayReplies(BaseModel):
    concepts: tuple[_Meaning, ...]
    relationship: _Relationship


@final
class _ReplaySource:
    def __init__(self, *, capture: ParsedPayload) -> None:
        self._capture = capture

    @asynccontextmanager
    async def open(
        self,
        *,
        origin: ParsedSourceOrigin,
        limits: ProcessingLimits,
    ) -> AsyncGenerator[ParsedPayload]:
        del limits
        if origin != self._capture.origin:
            raise SourceUnavailableError
        yield self._capture


def act_replay() -> tuple[ParsedSourceProvider, ParsedPayload]:
    """Bind marked source-checked passages when the full publisher PDF is absent."""
    source = next(item for item in load_sources() if item.id == "ai-act-en")
    selected = {"ai-3-actors", "ai-3-purpose", "ai-13-instructions", "ai-annex-recruitment"}
    capture = ParsedPayload(
        origin=ParsedSourceOrigin(
            provider=_PROVIDER,
            document_id="ai-act-selected-source-checked-paraphrases",
            document_revision=source.edition,
            captured_at=datetime(2026, 11, 17, tzinfo=UTC),
            claimed_original_digest=ContentHash(value=f"sha256:{_PROVIDED_DIGEST}"),
        ),
        parts=tuple(
            ParsedText(text=item.text, locator=ExternalLocation(key=item.id))
            for item in source.passages
            if item.id in selected
        ),
    )
    return ParsedSourceProvider(name=_PROVIDER, resolver=_ReplaySource(capture=capture)), capture


def guidance_replay() -> tuple[ParsedSourceProvider, ParsedPayload]:
    """Bind the source-checked summary of the exact separately attributed guide."""
    expected = _guidance_expectations()
    source = next(item for item in load_sources() if item.id == expected.source)
    if source.sha256 != expected.sha256 or source.edition != expected.edition:
        raise ValueError("Use the verified guidance edition in the source catalogue.")
    passage = next(item for item in source.passages if item.id == expected.concept.passage)
    capture = ParsedPayload(
        origin=ParsedSourceOrigin(
            provider=_GUIDANCE_PROVIDER,
            document_id="commission-guidance-source-checked-paraphrase",
            document_revision=source.edition,
            captured_at=datetime(2026, 11, 17, tzinfo=UTC),
            claimed_original_digest=ContentHash(value=f"sha256:{expected.sha256}"),
        ),
        parts=(ParsedText(text=passage.text, locator=ExternalLocation(key=passage.id)),),
    )
    return ParsedSourceProvider(
        name=_GUIDANCE_PROVIDER, resolver=_ReplaySource(capture=capture)
    ), capture


@final
class ReplayGateway(ModelGateway):
    """Return the authored replies for the three instruction modes."""

    def __init__(self) -> None:
        """Load only the labelled local transcript fixture."""
        self._guidance = _guidance_expectations()
        self._replies = _ReplayReplies.model_validate_json(
            (_FOLDER / "discovery-replies.json").read_bytes(),
        )

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Refer to the exact indexes in this extraction request."""
        evidence = tuple(item for chunk in request.inputs for item in chunk.evidence)
        indexes: dict[int | str, int] = {}
        for position, citation in enumerate(evidence, start=1):
            locator = citation.locator
            if isinstance(locator, DocumentSpan) and locator.page is not None:
                indexes[locator.page] = position
            elif isinstance(locator, ExternalLocation):
                indexes[locator.key] = position
        exact_guidance = f"sha256:{self._guidance.sha256}"
        revisions = {item.source for item in evidence}
        if any(
            item.revision_id.value == exact_guidance
            or (
                isinstance(item.origin, ParsedSourceOrigin)
                and item.origin.claimed_original_digest is not None
                and item.origin.claimed_original_digest.value == exact_guidance
            )
            for item in revisions
        ):
            concepts = (self._guidance.concept,)
            relationships: tuple[JsonValue, ...] = ()
        elif request.instructions == DOCUMENTATION_OVERRIDE:
            concepts = tuple(
                item for item in self._replies.concepts if item.name == "instructions-for-use"
            )
            relationships = ()
        else:
            concepts = tuple(
                item
                for item in self._replies.concepts
                if item.name != "candidate-evaluation-use"
                or RECRUITMENT_FOCUS in request.instructions
            )
            relation = self._replies.relationship
            relationships = (
                {
                    **relation.response(indexes=indexes),
                    "source": relation.source,
                    "target": relation.target,
                },
            )
        rows: tuple[JsonValue, ...] = tuple(item.response(indexes=indexes) for item in concepts)
        return ModelResponse(
            output_json=canonical_json_bytes(
                value={"concepts": rows, "relationships": relationships},
            ).decode(),
            model_id="authored/structured-discovery-replay",
        )
