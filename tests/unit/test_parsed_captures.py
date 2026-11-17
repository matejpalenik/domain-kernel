"""Check the normalized source wire contract independently of providers and persistence."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from domain_kernel import (
    CellValue,
    ExternalLocation,
    ParsedPayload,
    ParsedSourceOrigin,
    ParsedTable,
    ParsedText,
    ProcessingLimits,
)
from domain_kernel.sources.domain.parsed_codec import canonical_capture

_LIMITS = ProcessingLimits(
    max_source_bytes=4096,
    max_expanded_bytes=4096,
    max_concurrent_sources=1,
    max_pages=8,
)
_ORIGIN = ParsedSourceOrigin(
    provider="host",
    document_id="source-doc",
    document_revision="revision",
    captured_at=datetime(2026, 1, 1, tzinfo=UTC),
)
_FIRST = ExternalLocation(key="captured-table")


def test_capture_has_stable_wire_tags_and_time_independent_digest() -> None:
    columns = ["name", "value"]
    row: list[CellValue] = ["active", True]
    table = ParsedTable(name="Input", columns=columns, rows=[row], locator=_FIRST)
    columns.clear()
    row.clear()
    original = ParsedPayload(origin=_ORIGIN, parts=[table])
    later_time = _ORIGIN.captured_at + timedelta(days=1)
    later = replace(original, origin=replace(_ORIGIN, captured_at=later_time))
    canonical = canonical_capture(payload=original, limits=_LIMITS)
    assert canonical_capture(payload=later, limits=_LIMITS) == canonical
    assert b'"format":"normalized"' in canonical
    assert b'"kind":"supplied"' in canonical
    assert b'"schema_version":1' in canonical
    assert b"captured_at" not in canonical
    for changed in (
        replace(original, origin=replace(_ORIGIN, document_revision="different")),
        replace(original, parts=(replace(table, locator=ExternalLocation(key="elsewhere")),)),
        replace(original, parts=(replace(table, rows=(("active", 1),)),)),
    ):
        assert canonical_capture(payload=changed, limits=_LIMITS) != canonical


def test_scalar_types_have_distinct_normalized_values() -> None:
    values = (True, 1, 1.0, "1", Decimal(1), date(2026, 1, 1), _ORIGIN.captured_at)
    captures = [
        canonical_capture(
            payload=ParsedPayload(
                origin=_ORIGIN,
                parts=[
                    ParsedTable(name="Values", columns=["value"], rows=[[value]], locator=_FIRST)
                ],
            ),
            limits=_LIMITS,
        )
        for value in values
    ]
    assert len(set(captures)) == len(values)


def test_capture_requires_distinct_locators_and_rectangular_rows() -> None:
    with pytest.raises(ValueError, match="rectangular"):
        _ = ParsedTable(name="Table", columns=["a", "b"], rows=[[1]], locator=_FIRST)
    with pytest.raises(ValueError, match="finite"):
        _ = ParsedTable(name="Table", columns=["a"], rows=[[float("inf")]], locator=_FIRST)
    with pytest.raises(ValueError, match="unique locator"):
        _ = ParsedPayload(
            origin=_ORIGIN,
            parts=[ParsedText(text="One", locator=_FIRST), ParsedText(text="Two", locator=_FIRST)],
        )
