"""Canonical capture bytes with stable wire tags independent of Python type names."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from domain_kernel.shared.canonical_json import CanonicalJson
from domain_kernel.shared.domain.codecs.decimal_text import DecimalText
from domain_kernel.shared.domain.value_objects.blank_node import BlankNode
from domain_kernel.shared.domain.value_objects.iri import Iri
from domain_kernel.shared.errors.resource_limit_error import ResourceLimitError
from domain_kernel.sources.domain.parsed import (
    DocumentSpan,
    ExternalLocation,
    ParsedGraph,
    ParsedTable,
    ParsedText,
    StatementSpan,
)

if TYPE_CHECKING:
    from domain_kernel.shared.domain.value_objects.rdf_literal import RdfLiteral
    from domain_kernel.shared.json_value import JsonValue
    from domain_kernel.sources.domain.models import ProcessingLimits
    from domain_kernel.sources.domain.parsed import (
        CellValue,
        EvidenceLocator,
        ParsedPart,
        ParsedPayload,
    )


def _locator(*, value: EvidenceLocator) -> JsonValue:
    if isinstance(value, ExternalLocation):
        return {"kind": "external", "key": value.key}
    if isinstance(value, DocumentSpan):
        return {
            "kind": "document_span",
            "start": value.start,
            "end": value.end,
            "page": value.page,
            "section": value.section,
        }
    if isinstance(value, StatementSpan):
        return {"kind": value.kind, "start": value.start, "end": value.end}
    return {"kind": "cells", "sheet": value.sheet, "cells": value.cells}


def _term(*, value: Iri | BlankNode | RdfLiteral | None) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Iri):
        return {"kind": "iri", "value": value.value}
    if isinstance(value, BlankNode):
        return {"kind": "blank_node", "id": value.id}
    return {
        "kind": "literal",
        "value": value.value,
        "language": value.language,
        "datatype": None if value.datatype is None else value.datatype.value,
    }


def _scalar(*, value: CellValue) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        kind = {type(None): "null", bool: "boolean", int: "integer", str: "string"}[type(value)]
        return {"kind": kind, "value": value}
    if isinstance(value, float):
        return {"kind": "float", "value": value.hex()}
    if isinstance(value, datetime):
        return {"kind": "datetime", "value": value.astimezone(UTC).isoformat()}
    if isinstance(value, date):
        return {"kind": "date", "value": value.isoformat()}
    return {"kind": "decimal", "value": DecimalText.canonical_decimal_text(value=value)}


def part_value(*, part: ParsedPart) -> JsonValue:
    """Represent one exact supplied part using only its declared wire fields."""
    locator = _locator(value=part.locator)
    if isinstance(part, ParsedText):
        return {"kind": "text", "locator": locator, "text": part.text}
    if isinstance(part, ParsedTable):
        return {
            "kind": "table",
            "locator": locator,
            "name": part.name,
            "columns": part.columns,
            "rows": tuple(tuple(_scalar(value=cell) for cell in row) for row in part.rows),
            "row_locators": tuple(_locator(value=item) for item in part.row_locators),
        }
    return {
        "kind": "graph",
        "locator": locator,
        "statements": tuple(
            {
                "subject": _term(value=item.subject),
                "predicate": _term(value=item.predicate),
                "object": _term(value=item.object),
                "graph": _term(value=item.graph),
            }
            for item in part.statements
        ),
    }


def _check_limits(*, payload: ParsedPayload, limits: ProcessingLimits) -> None:
    maximum = min(limits.max_source_bytes, limits.max_expanded_bytes)
    approximate_bytes = 0
    for part in payload.parts:
        locators = (part.locator,)
        if isinstance(part, ParsedText):
            approximate_bytes += len(part.text)
        elif isinstance(part, ParsedGraph):
            approximate_bytes += len(part.statements)
        else:
            approximate_bytes += len(part.columns) * len(part.rows)
            locators = (*locators, *part.row_locators)
        if approximate_bytes > maximum:
            raise ResourceLimitError(message="Supply a smaller parsed capture.")
        if any(
            isinstance(item, DocumentSpan)
            and item.page is not None
            and item.page > limits.max_pages
            for item in locators
        ):
            raise ResourceLimitError(
                message="Use parsed page locators within the configured limit."
            )


def canonical_capture(*, payload: ParsedPayload, limits: ProcessingLimits) -> bytes:
    """Hash normalized content independently of the time the host captured it."""
    _check_limits(payload=payload, limits=limits)
    origin = payload.origin
    claimed = origin.claimed_original_digest
    wire = CanonicalJson.encode(
        value={
            "format": "normalized",
            "schema_version": payload.schema_version,
            "origin": {
                "kind": "supplied",
                "provider": origin.provider,
                "document_id": origin.document_id,
                "document_revision": origin.document_revision,
                "claimed_original_digest": None if claimed is None else claimed.value,
            },
            "parts": tuple(part_value(part=item) for item in payload.parts),
        },
    )
    if len(wire) > min(limits.max_source_bytes, limits.max_expanded_bytes):
        raise ResourceLimitError(
            message="Supply a parsed capture within the configured byte limit."
        )
    return wire
