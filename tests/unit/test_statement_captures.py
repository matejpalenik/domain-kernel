"""Check strict statement inputs and the stable attribution digest."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from domain_kernel import (
    Person,
    PersonId,
    ProcessingLimits,
    Statement,
    StatementForm,
    StatementIntent,
)
from domain_kernel.sources.application.statements import attributed_payload, canonical_statement

_SPEAKER = Person(id=PersonId(value="owner"), name="Ari", role="Model owner")
_LIMITS = ProcessingLimits(
    max_source_bytes=4096,
    max_expanded_bytes=4096,
    max_concurrent_sources=1,
    max_pages=1,
)


def test_statement_hash_uses_resolved_attribution_but_excludes_the_recording_clock() -> None:
    source = Statement(
        speaker=_SPEAKER,
        text="This field is assigned locally.",
        context="Internal references",
        form=StatementForm.SUMMARY,
        intent=StatementIntent.OBSERVATION,
    )
    first = attributed_payload(statement=source, actor="recorder")
    same = replace(
        first,
        origin=replace(first.origin, recorded_at=first.origin.recorded_at + timedelta(days=2)),
    )
    canonical = canonical_statement(payload=first, limits=_LIMITS)
    assert b'"stated_at":null' in canonical
    assert canonical == canonical_statement(payload=same, limits=_LIMITS)
    for changed in (
        replace(first.origin, context="Public references"),
        replace(first.origin, recorded_by="other"),
        replace(first.origin, stated_at=datetime(2026, 11, 17, tzinfo=UTC)),
    ):
        assert canonical != canonical_statement(
            payload=replace(first, origin=changed),
            limits=_LIMITS,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"recorded_by": " "},
        {"context": ""},
        {"form": None},
        {"intent": "observation"},
        {"stated_at": datetime(2026, 11, 17)},  # noqa: DTZ001 - Reject naive inputs.
    ],
)
def test_statement_rejects_untyped_or_incomplete_attribution(change: dict[str, object]) -> None:
    fields = {
        "speaker": _SPEAKER,
        "text": "Private statement text.",
        "context": "Internal references",
        "form": StatementForm.SUMMARY,
        "intent": StatementIntent.OBSERVATION,
    }
    with pytest.raises(ValidationError) as error:
        _ = Statement.model_validate({**fields, **change})
    assert "Private statement text." not in str(error.value)
