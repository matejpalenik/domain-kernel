"""Capture the host's modeling inputs for v23 discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain_kernel._shared.domain.record_encoding import record_value

if TYPE_CHECKING:
    from domain_kernel.discovery.domain.models import DiscoveryDraft

_REVIEW_PROMPTS = (
    "What distinguishes two examples of the same kind?",
    "Which roles and directions are involved?",
    "When does the statement apply, and what are its exceptions?",
    "Which source establishes that interpretation, under whose authority and when?",
)


def purpose(*, draft: DiscoveryDraft) -> dict[str, object]:
    """Expose the typed scope separately from authoritative stage instructions."""
    options = draft.prompt.schema_options
    if options is None:
        return {}
    return {
        "competency_questions": [
            {"id": q.id, "text": q.text} for q in options.competency_questions
        ],
        "source_context": [record_value(value=item) for item in options.source_context],
        "as_of": options.as_of.isoformat() if options.as_of else None,
        "review_prompts": _REVIEW_PROMPTS,
    }
