"""Exercise real notebook review controls through the SDK's persistence boundary."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from domain_kernel import (
    Accept,
    CaseStatus,
    Client,
    ClientConfiguration,
    ConceptDefinition,
    DomainKernelError,
    Model,
    ModelKind,
    ReviewCase,
    ReviewReceipt,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain_kernel.review.domain.decisions import ReviewAction

pytestmark = [pytest.mark.integration, pytest.mark.notebook, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def pending_review(tmp_path: Path) -> tuple[Model, ReviewCase]:
    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor", name="frontend"
    )
    model = await project.create_model(
        actor="editor",
        name="recruitment",
        kind=ModelKind.PROPOSED,
        description="Review recruitment.",
    )
    case = await model.propose_definition(
        actor="editor",
        name="review-channel",
        meaning="Where the application records a review.",
        body=ConceptDefinition(),
        reason="Inspect the review channel.",
    )
    return model, case


async def test_review_controls_require_a_fresh_preview_and_keep_attribution(
    pending_review: tuple[Model, ReviewCase],
) -> None:
    from examples.notebooks.live_controls import ReviewControls  # noqa: PLC0415

    model, case = pending_review
    control = ReviewControls(model=model, case=case, actor="widget-reviewer")
    assert control.submit.disabled
    control.reason.value = "The concept matches the application scope."
    control.preview.click()
    await control.wait()
    assert not control.submit.disabled
    assert (await model.get_review_case(case_id=case.id)).status is CaseStatus.PENDING
    control.reason.value = "The new reason needs its own preview."
    assert control.submit.disabled
    control.preview.click()
    await control.wait()
    control.submit.click()
    control.submit.click()
    await control.wait()
    history = await model.get_review_history(case_id=case.id)
    (receipt,) = history.items
    assert receipt.actor == "widget-reviewer"
    assert "Decision recorded" in control.status.value
    assert control.submit.disabled


async def test_review_controls_refresh_when_the_case_changes(
    pending_review: tuple[Model, ReviewCase],
) -> None:
    from examples.notebooks.live_controls import ReviewControls  # noqa: PLC0415

    model, case = pending_review
    control = ReviewControls(model=model, case=case, actor="widget-reviewer")
    control.reason.value = "Review the pending definition."
    control.preview.click()
    await control.wait()
    _ = await model.decide_review(
        actor="backend-reviewer", case=case, decision=Accept(reason="Agreed.")
    )
    control.submit.click()
    await control.wait()
    assert "Refresh" in control.status.value
    assert control.submit.disabled
    control.refresh.click()
    await control.wait()
    assert "resolved" in control.status.value
    (receipt,) = (await model.get_review_history(case_id=case.id)).items
    assert receipt.actor == "backend-reviewer"


async def test_review_controls_retry_the_same_committed_intent_after_an_uncertain_response(
    pending_review: tuple[Model, ReviewCase],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from examples.notebooks.live_controls import ReviewControls  # noqa: PLC0415

    model, case = pending_review
    real_decide = Model.decide_review
    keys: list[str | None] = []
    committed = asyncio.Event()
    reply = asyncio.Event()

    async def interrupted(
        self: Model,
        *,
        actor: str,
        case: ReviewCase,
        decision: ReviewAction,
        idempotency_key: str | None = None,
    ) -> ReviewReceipt:
        keys.append(idempotency_key)
        receipt = await real_decide(
            self, actor=actor, case=case, decision=decision, idempotency_key=idempotency_key
        )
        if len(keys) == 1:
            committed.set()
            _ = await reply.wait()
            raise DomainKernelError(
                code="receipt_unavailable", message="Retry the same intent.", retryable=True
            )
        return receipt

    monkeypatch.setattr(Model, "decide_review", interrupted)
    control = ReviewControls(model=model, case=case, actor="widget-reviewer")
    control.reason.value = "Review the selected handoff channel."
    control.preview.click()
    await control.wait()
    control.submit.click()
    try:
        async with asyncio.timeout(5):
            _ = await committed.wait()
        assert control.submit.disabled
        control.submit.click()
        assert len(keys) == 1
    finally:
        reply.set()
        await control.wait()
    assert not control.submit.disabled
    control.submit.click()
    await control.wait()
    assert keys[0] is not None
    assert keys == [keys[0], keys[0]]
    (receipt,) = (await model.get_review_history(case_id=case.id)).items
    assert receipt.actor == "widget-reviewer"


async def test_evidence_summary_does_not_reveal_the_resolved_excerpt(tmp_path: Path) -> None:
    from domain_kernel import (  # noqa: PLC0415
        Person,
        PersonId,
        Statement,
        StatementForm,
        StatementIntent,
        render_notebook,
    )

    project = await Client(config=ClientConfiguration(base_dir=tmp_path)).create_project(
        actor="editor", name="frontend"
    )
    received = await project.ingest_source(
        actor="editor",
        name="disposable-clarification",
        source=Statement(
            text="A private recruiting policy excerpt.",
            speaker=Person(id=PersonId(value="author"), name="The author", role="Editor"),
            context="The exact evidence selected for inspection.",
            form=StatementForm.QUOTATION,
            intent=StatementIntent.ASSERTION,
        ),
    )
    resolved = await project.get_evidence(evidence=received.evidence[0])
    summary = render_notebook(value=resolved)
    assert resolved.evidence.id.value in summary
    assert resolved.evidence.source.revision_id.value in summary
    assert resolved.excerpt not in summary
