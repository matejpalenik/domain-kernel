"""Exercise exact mention identities and qualification scope without inference."""

from __future__ import annotations

from dataclasses import replace

from domain_kernel.discovery.application.claim_extraction import (
    Anchor,
    LinkedQualifier,
    MentionInput,
)
from domain_kernel.discovery.application.evidence_binding import locate_mention, qualifier_paths
from domain_kernel.sources.domain.parsed import DocumentSpan
from tests.support.discovery import make_request


def test_repeated_words_require_context_and_overlapping_chunks_share_identity() -> None:
    text = "Candidate may sign. Candidate must return."
    original = make_request(name="roles", text=text, scope="Roles", arm="test").inputs[0]
    evidence = original.evidence[0]
    page = replace(
        original,
        evidence=(replace(evidence, locator=DocumentSpan(page=1, start=0, end=len(text))),),
    )
    chunk = replace(original, text="Candidate must return.")
    parts = {1: page, 2: chunk}
    repeated = MentionInput(
        ref="candidate",
        anchor=Anchor(citation=1, quote="Candidate"),
        context=None,
        role=None,
        approved_name=None,
    )
    assert (
        locate_mention(
            mention=repeated, index=1, part=parts.__getitem__, canonical=(), approved=set()
        )
        is None
    )
    second = repeated.model_copy(update={"context": "Candidate must return."})
    canonical = locate_mention(
        mention=second, index=1, part=parts.__getitem__, canonical=(), approved=set()
    )
    overlap = locate_mention(
        mention=second, index=2, part=parts.__getitem__, canonical=(1,), approved=set()
    )
    assert canonical is not None
    assert overlap == canonical
    assert text[canonical.start : canonical.end] == "Candidate"
    first = repeated.model_copy(update={"context": "Candidate may sign."})
    other = locate_mention(
        mention=first, index=1, part=parts.__getitem__, canonical=(), approved=set()
    )
    assert other is not None
    assert other.id != canonical.id


def test_qualifier_identity_preserves_scope_and_rejects_cycles() -> None:
    exception = LinkedQualifier(
        ref="exception", kind="exception", text="Derogation", applies_to=None, evidence=[]
    )
    override = LinkedQualifier(
        ref="override", kind="override", text="Profiling", applies_to="exception", evidence=[]
    )
    assert qualifier_paths((exception, override)) == (
        ("exception", "Derogation"),
        ("exception", "Derogation", "override", "Profiling"),
    )
    assert (
        qualifier_paths((exception, override.model_copy(update={"applies_to": "unknown"}))) is None
    )
    assert (
        qualifier_paths((exception.model_copy(update={"applies_to": "override"}), override)) is None
    )
