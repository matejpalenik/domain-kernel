"""Project exact, selectable spans from pinned capture, without changing its locators."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from domain_kernel.discovery.application.omission_windows import (
    Window,
    partition,
    table_field,
    table_header,
)
from domain_kernel.discovery.domain.bindings import BindingWitness
from domain_kernel.discovery.domain.schema_evidence import SchemaRecordBinding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from domain_kernel.discovery.application.contracts.inference_input import InferenceInput
    from domain_kernel.sources.domain.models import Evidence

_LINES = re.compile(r"[^\r\n]+")
_NUMBERED_HEADING = re.compile(r"(\d+(?:\.\d+)*\.|\d+(?:\.\d+)+)\s+\S")
_MARKDOWN_HEADING = re.compile(r"(#{1,6})\s+\S")
_WIDTH = 384


@dataclass(frozen=True, kw_only=True, slots=True)
class Span:
    """An exact occurrence within the original captured excerpt, not a file offset."""

    id: str
    passage: int
    start: int
    end: int
    evidence: Evidence
    quote: str
    scope: tuple[int, ...] = ()
    heading: bool = False
    row: int | None = None
    column: int | None = None

    def witness(self) -> BindingWitness:
        """Return the existing review representation of this exact occurrence."""
        return BindingWitness(evidence=self.evidence, quote=self.quote)

    def receipt(self) -> dict[str, str | int]:
        """Keep the original capture identity alongside its slice offsets."""
        return {
            "id": self.id,
            "passage": self.passage,
            "start": self.start,
            "end": self.end,
            "evidence_id": self.evidence.id.value,
            "processing_fingerprint": self.evidence.processing.fingerprint,
        }


def bind_record(*, anchor: Span, source: Span, target: Span) -> SchemaRecordBinding | None:
    """Check one captured row or explicit heading scope, never mere page proximity."""
    if (
        source == target
        or anchor.passage != source.passage
        or source.passage != target.passage
        or anchor.evidence != source.evidence
        or source.evidence != target.evidence
    ):
        return None
    if anchor.row is not None:
        if not anchor.row == source.row == target.row:
            return None
    else:
        common = anchor.scope
        shorter, longer = sorted((source.scope, target.scope), key=len)
        if not (
            anchor.heading
            and common
            and shorter[: len(common)] == common
            and longer[: len(shorter)] == shorter
        ):
            return None
    return SchemaRecordBinding(
        anchor=anchor.witness(), source=source.witness(), target=target.witness()
    )


@dataclass(frozen=True, kw_only=True)
class Inventory:
    """Only addresses in this projection may be returned in this request."""

    spans: dict[str, Span]
    inputs: tuple[InferenceInput, ...]

    @classmethod
    def issue(cls, *, corpus: tuple[InferenceInput, ...], selected: tuple[int, ...]) -> Inventory:
        """Build stable aliases only for the parents selected for this request."""
        issued: dict[str, Span] = {}
        for i in selected:
            part = corpus[i]
            if len(part.evidence) != 1:
                continue
            rows = _cells(text=part.text) if part.is_table else _prose(text=part.text)
            for ordinal, (start, end, scope, heading, row, column) in enumerate(rows, 1):
                key = f"E{i + 1}.{ordinal}"
                issued[key] = Span(
                    id=key,
                    passage=i + 1,
                    start=start,
                    end=end,
                    evidence=part.evidence[0],
                    quote=part.text[start:end],
                    scope=scope,
                    heading=heading,
                    row=row,
                    column=column,
                )
        by_passage = _by_passage(spans=issued)
        return cls(
            spans=issued,
            inputs=tuple(
                _render(part=corpus[i], spans=by_passage.get(i + 1, [])) for i in selected
            ),
        )

    def restrict(
        self, *, corpus: tuple[InferenceInput, ...], ids: set[str], byte_limit: int
    ) -> Inventory:
        """Render only offered options, keeping even the annotations within the budget."""
        spans = {key: row for key, row in self.spans.items() if key in ids}
        offered: dict[str, Span] = {}
        inputs: list[InferenceInput] = []
        for passage, rows in _by_passage(spans=spans).items():
            part = _render(part=corpus[passage - 1], spans=rows)
            size = len(part.text.encode())
            if size <= byte_limit:
                byte_limit -= size
                inputs.append(part)
                offered.update((row.id, row) for row in rows)
        return Inventory(spans=offered, inputs=tuple(inputs))


def _by_passage(*, spans: dict[str, Span]) -> dict[int, list[Span]]:
    grouped: dict[int, list[Span]] = defaultdict(list)
    for span in spans.values():
        grouped[span.passage].append(span)
    return grouped


type _Slice = tuple[int, int, tuple[int, ...], bool, int | None, int | None]


def _prose(*, text: str) -> Iterator[_Slice]:
    # A new top-level or sibling heading starts a new scope even if its label repeats.
    numbered: list[tuple[tuple[str, ...], int]] = []
    markdown: list[tuple[int, int]] = []
    for line in _LINES.finditer(text):
        value = line[0].strip()
        if not value:
            continue
        start = line.start() + len(line[0]) - len(line[0].lstrip())
        end = start + len(value)
        heading = False
        if match := _NUMBERED_HEADING.match(value):
            path = tuple(match[1].rstrip(".").split("."))
            while numbered and path[: len(numbered[-1][0])] != numbered[-1][0]:
                _ = numbered.pop()
            if numbered and numbered[-1][0] == path:
                _ = numbered.pop()
            numbered.append((path, start))
            heading = True
        elif match := _MARKDOWN_HEADING.match(value):
            numbered.clear()
            level = len(match[1])
            while markdown and markdown[-1][0] >= level:
                _ = markdown.pop()
            markdown.append((level, start))
            heading = True
        scope = tuple(offset for _, offset in (*markdown, *numbered))
        for item in partition(
            text=text, window=Window(citation=1, start=start, end=end), width=_WIDTH
        ):
            yield item.start, item.end, scope, heading and item.start == start, None, None


def _cells(*, text: str) -> Iterator[_Slice]:
    start, end = table_field(text=text, name="rows")
    pos = start + 1
    row = 0
    decode = json.JSONDecoder().raw_decode
    while pos < end - 1:
        row += 1
        pos += 1  # Opening row bracket.
        column = 0
        while text[pos] != "]":
            column += 1
            stop = decode(text, pos)[1]
            yield pos, stop, (), False, row, column
            pos = stop
            if text[pos] == ",":
                pos += 1
        pos += 2  # Closing row bracket and optional comma.


def _render(*, part: InferenceInput, spans: list[Span]) -> InferenceInput:
    if not spans:
        return part
    if not part.is_table:
        return replace(part, text="\n".join(f"[{item.id}] {item.quote}" for item in spans))
    lines = [table_header(text=part.text)]
    row = None
    for item in spans:
        if row != item.row:
            row = item.row
            lines.append(f"Row {row}:")
        lines.append(f"[{item.id}] column {item.column}: {item.quote}")
    return replace(part, text="\n".join(lines))
