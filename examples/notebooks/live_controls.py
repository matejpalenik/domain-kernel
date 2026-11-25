"""Example notebook controls over exact published records and ordinary SDK review calls."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html import escape
from itertools import islice
from typing import TYPE_CHECKING, final
from uuid import uuid4

import ipywidgets as widgets

from domain_kernel import (
    Accept,
    CaseStatus,
    ConceptDefinition,
    DomainKernelError,
    ModelKind,
    ModelNotFoundError,
    Reject,
    StaleStateError,
    render_notebook,
)
from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from domain_kernel import DomainModelBundle, Model, Project, ReviewCase

_MAX_MATCHES = 20
_REVIEW_REASON = "Review a local handoff channel for the recruitment contract."


def inspect_release(*, release: DomainModelBundle) -> widgets.VBox:
    """Filter one loaded release and inspect the selected immutable definition."""
    definitions = {item.id.value: item for item in release.content.definitions}
    search = widgets.Text(description="Search definitions", placeholder="Lookup name or label")
    selection = widgets.Dropdown(description="Definition")
    summary = widgets.HTML()

    def show(_change: object) -> None:
        selected = selection.value
        definition = definitions.get(selected) if isinstance(selected, str) else None
        summary.value = (
            render_notebook(value=definition)
            if definition is not None
            else '<p role="status">No definitions match this search.</p>'
        )

    def filter_defs(_change: object) -> None:
        query = search.value.casefold().strip()
        previous = selection.value
        options = tuple(
            islice(
                (
                    (item.display_name, item.id.value)
                    for item in definitions.values()
                    if query in item.name.casefold() or query in item.display_name.casefold()
                ),
                _MAX_MATCHES,
            )
        )
        selection.options = options
        if not options:
            selection.value = None
        elif any(identity == previous for _, identity in options):
            selection.value = previous
        else:
            selection.value = options[0][1]
        show(None)

    search.observe(filter_defs, names="value")
    selection.observe(show, names="value")
    filter_defs(None)
    return widgets.VBox(
        [
            widgets.HTML(value=f"<p>Release {escape(release.version)} · up to 20 matches</p>"),
            search,
            selection,
            summary,
        ]
    )


@dataclass(frozen=True, kw_only=True)
class _ReviewIntent:
    case: ReviewCase
    decision: Accept | Reject
    key: str


@final
class ReviewControls:
    """Preview and explicitly submit one exact review intent using the host actor."""

    def __init__(self, *, model: Model, case: ReviewCase, actor: str) -> None:
        """Capture the inspected case and build inert controls."""
        TextValidation.require_text(value=actor, field="Review actor")
        self._model = model
        self._case = case
        self._actor = actor
        self._intent: _ReviewIntent | None = None
        self._task: asyncio.Task[None] | None = None
        self._busy = False
        self._refresh_required = False
        self._finished = case.status is not CaseStatus.PENDING
        self.choice = widgets.Dropdown(description="Decision", options=["Accept", "Reject"])
        self.reason = widgets.Text(description="Review reason")
        self.preview = widgets.Button(description="Preview review")
        self.submit = widgets.Button(description="Submit review")
        self.refresh = widgets.Button(description="Refresh case")
        self.status = widgets.HTML()
        self.impact = widgets.HTML()
        self.widget = widgets.VBox(
            [
                widgets.HTML(value=f"<p>Reviewer {escape(actor)}</p>"),
                self.choice,
                self.reason,
                widgets.HBox([self.preview, self.submit, self.refresh]),
                self.status,
                self.impact,
            ]
        )
        self.choice.observe(self._changed, names="value")
        self.reason.observe(self._changed, names="value")
        self.preview.on_click(lambda _: self._launch(work=self._preview))
        self.submit.on_click(lambda _: self._launch(work=self._submit))
        self.refresh.on_click(lambda _: self._launch(work=self._refresh))
        self._show(message=f"Case status: {case.status.value}.")
        self._buttons()

    def _show(self, *, message: str) -> None:
        self.status.value = f'<p role="status" aria-live="polite">{escape(message)}</p>'

    def _buttons(self) -> None:
        blocked = self._busy or self._refresh_required or self._finished
        self.choice.disabled = blocked
        self.reason.disabled = blocked
        self.preview.disabled = blocked or not self.reason.value.strip()
        self.submit.disabled = blocked or self._intent is None
        self.refresh.disabled = self._busy

    def _changed(self, _change: object) -> None:
        self._intent = None
        self.impact.value = ""
        self._show(message="Preview this review intent before submitting.")
        self._buttons()

    def _launch(self, *, work: Callable[[], Coroutine[object, object, None]]) -> None:
        if self._busy:
            return
        self._busy = True
        self._buttons()
        self._task = asyncio.create_task(self._run(work=work))

    async def _run(self, *, work: Callable[[], Coroutine[object, object, None]]) -> None:
        try:
            await work()
        except StaleStateError:
            self._intent = None
            self._refresh_required = True
            self.impact.value = ""
            self._show(message="The review snapshot changed. Refresh the case before continuing.")
        except DomainKernelError as error:
            if not error.retryable:
                self._intent = None
            self._show(
                message="Review could not complete. Inspect the case or retry the saved intent."
            )
        finally:
            self._busy = False
            self._buttons()

    async def wait(self) -> None:
        """Wait for the action requested through a button."""
        if self._task is not None:
            await self._task

    async def _preview(self) -> None:
        reason = self.reason.value.strip()
        if self._refresh_required or self._finished or not reason:
            return
        decision = Accept(reason=reason) if self.choice.value == "Accept" else Reject(reason=reason)
        self._intent = None
        impact = await self._model.preview_changes(case=self._case, decision=decision)
        self.impact.value = render_notebook(value=impact)
        if impact.blockers:
            self._show(message="Resolve the blocking findings before you submit.")
        else:
            self._intent = _ReviewIntent(case=self._case, decision=decision, key=uuid4().hex)
            self._show(message="Preview ready for explicit submission.")

    async def _submit(self) -> None:
        intent = self._intent
        if intent is None or self._finished or self._refresh_required:
            return
        receipt = await self._model.decide_review(
            actor=self._actor,
            case=intent.case,
            decision=intent.decision,
            idempotency_key=intent.key,
        )
        self._finished = True
        self._intent = None
        self._show(
            message=f"Decision recorded by {self._actor}. Case version {receipt.case_version}."
        )

    async def _refresh(self) -> None:
        self._case = await self._model.get_review_case(case_id=self._case.id)
        self._finished = self._case.status is not CaseStatus.PENDING
        self._refresh_required = False
        self._intent = None
        self.impact.value = ""
        self._show(message=f"Case status: {self._case.status.value}.")


async def demo_review(*, project: Project) -> tuple[Model, ReviewCase]:
    """Prepare a separate sample case through the public authoring API."""
    try:
        workspace = await project.get_model(name="notebook-handoff-review")
    except ModelNotFoundError:
        workspace = await project.create_model(
            actor="demo:developer",
            name="notebook-handoff-review",
            kind=ModelKind.PROPOSED,
            description="A separate review of the recruitment contract handoff.",
        )
    case = await workspace.propose_definition(
        actor="demo:developer",
        name="handoff-channel",
        meaning="The channel that delivers the reviewed contract to the receiving application.",
        body=ConceptDefinition(),
        reason=_REVIEW_REASON,
        idempotency_key="notebook-demo-handoff",
    )
    return workspace, await workspace.get_review_case(case_id=case.id)
