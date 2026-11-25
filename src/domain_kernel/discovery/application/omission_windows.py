"""Bounded subdivisions of already captured omission evidence."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from domain_kernel.discovery.application.claim_extraction import ClosedRecord, normalized
from domain_kernel.discovery.domain.coverage import DiscoveryCoverage, DiscoveryWindow
from domain_kernel.shared.errors import InferenceError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel._shared.application.inference import InferenceInput
    from domain_kernel.discovery.application.claim_extraction import Claim
    from domain_kernel.sources.domain.models import SourceRevision

VERSION = "omission-windows-v1"
MAX_CHARS = 2048
MIN_CHARS = 512
MAX_CALLS = 8
MAX_TOKENS = 16_384
_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+")
_SPACE = re.compile(r"\s+")


class Window(ClosedRecord):
    """Exact offsets relative to an issued parent input."""

    citation: int
    start: int
    end: int


class WindowReceipt(Window):
    """Outcome of processing a source span."""

    reason: str | None = None


class WindowManifest(ClosedRecord):
    """Detached coverage handoff from the staged discovery gateway."""

    windows: list[WindowReceipt]


def partition(*, text: str, window: Window, width: int) -> list[Window]:
    """Split at sentence or clause boundaries, retaining a disjoint whole-span cover."""
    start = window.start
    rows: list[Window] = []
    while start < window.end:
        end = min(window.end, start + width)
        if end < window.end:
            # Both children must make progress even on prose without whitespace.
            lower = start + width // 2
            boundaries = list(_BOUNDARY.finditer(text, lower, end))
            if not boundaries:
                boundaries = list(_SPACE.finditer(text, lower, end))
            if boundaries:
                end = boundaries[-1].end()
        rows.append(Window(citation=window.citation, start=start, end=end))
        start = end
    return rows


def table_field(*, text: str, name: str) -> tuple[int, int]:
    """Locate a top-level value in the SDK's canonical captured table."""
    # Captured tables use compact canonical JSON. Walk top-level members so a cell
    # containing the field name cannot be mistaken for a structural boundary.
    decoder = json.JSONDecoder()
    position = 1
    while position < len(text) - 1:
        end = decoder.raw_decode(text, position)[1]
        key = text[position:end]
        start = end + 1
        end = decoder.raw_decode(text, start)[1]
        if key == f'"{name}"':
            return start, end
        position = end + 1
    raise ValueError("Read the canonical table fields of the captured excerpt.")


def table_header(*, text: str) -> str:
    """Read column labels from their exact bytes in the capture."""
    start, end = table_field(text=text, name="columns")
    return '"columns":' + text[start:end]


def table_windows(*, text: str, window: Window) -> list[Window]:
    """Partition one captured table at row boundaries, retaining exact offsets."""
    start, end = table_field(text=text, name="rows")
    position = start + 1
    decoder = json.JSONDecoder()
    cuts = [window.start]
    while position < end - 1:
        if window.start < position < window.end and position != start + 1:
            cuts.append(position)
        row_end = decoder.raw_decode(text, position)[1]
        position = row_end + 1
    return [
        Window(citation=window.citation, start=a, end=b)
        for a, b in zip(cuts, [*cuts[1:], window.end], strict=True)
    ]


def covers(*, claim: Claim, text: str) -> bool:
    """Admit only assertions whose evidence all occurs in the dispatched window."""
    excerpt = normalized(text)
    return all(
        a.citation == 1 and bool(normalized(a.quote)) and normalized(a.quote) in excerpt
        for q in (claim, *claim.conditions, *claim.exceptions)
        for a in q.evidence
    )


def decode(*, content: str, inputs: Sequence[InferenceInput]) -> tuple[DiscoveryCoverage, ...]:
    """Validate the handoff against the original evidence before persisting it."""
    from pydantic import ValidationError  # noqa: PLC0415 - Keep response validation at the boundary.

    try:
        return _coverage(manifest=WindowManifest.model_validate_json(content), inputs=inputs)
    except (ValidationError, ValueError, TypeError):
        raise InferenceError(
            message="Use coverage windows from the pinned evidence inventory."
        ) from None


def _coverage(
    *, manifest: WindowManifest, inputs: Sequence[InferenceInput]
) -> tuple[DiscoveryCoverage, ...]:
    by_source: dict[SourceRevision, list[DiscoveryWindow]] = {
        part.evidence[0].source: [] for part in inputs
    }
    for item in manifest.windows:
        if not 1 <= item.citation <= len(inputs):
            raise ValueError("Use an issued window citation.")
        part = inputs[item.citation - 1]
        if not 0 <= item.start < item.end <= len(part.text):
            raise ValueError("Use offsets within the original excerpt.")
        source = part.evidence[0]
        by_source[source.source].append(
            DiscoveryWindow(
                evidence=source,
                start=item.start,
                end=item.end,
                completed=item.reason is None,
                reason=item.reason,
            )
        )
    return tuple(
        DiscoveryCoverage(source=source, windows=tuple(windows))
        for source, windows in by_source.items()
    )
