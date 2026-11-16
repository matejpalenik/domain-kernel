"""Bounded teaching questions and feedback; no SDK execution or review mutations."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from examples.notebooks._preview.catalogue import FrozenRecord, load_catalogue, load_sources
from examples.notebooks._preview.models import Panel
from examples.notebooks._preview.rendering import render_table

if TYPE_CHECKING:
    from collections.abc import Mapping


class Option(FrozenRecord):
    """One authored answer and its misconception-specific feedback."""

    value: str
    label: str
    feedback: str


class PracticeField(FrozenRecord):
    """A selection or exact-name lookup task; no arbitrary code evaluation."""

    key: str
    label: str
    answer: str
    correct_feedback: str
    hint: str
    options: tuple[Option, ...]
    fallback_feedback: str


class FieldFeedback(FrozenRecord):
    """Feedback tied to what the learner actually supplied."""

    label: str
    value: str
    status: Literal["correct", "try again", "unanswered"]
    message: str


class PracticeResult(FrozenRecord):
    """Teaching feedback, deliberately distinct from an SDK validation report."""

    fields: tuple[FieldFeedback, ...]

    @property
    def solved(self) -> bool:
        """Require every response to match the authored exercise contract."""
        return bool(self.fields) and all(field.status == "correct" for field in self.fields)


class Practice(FrozenRecord):
    """An immutable exercise with a worked answer available offline."""

    id: str
    chapter: Literal["C4", "C6", "C7"]
    title: str
    prompt: str
    fields: tuple[PracticeField, ...]
    outcome: str
    solution: str
    evidence: tuple[str, ...]

    def check(self, *, answers: Mapping[str, str]) -> PracticeResult:
        """Compare authored choices only; never execute entered text."""
        feedback: list[FieldFeedback] = []
        for field in self.fields:
            value = answers.get(field.key, "").strip()
            option = next((item for item in field.options if item.value == value), None)
            if not value:
                status, message = "unanswered", "Choose or enter an answer, then check it."
            elif value == field.answer:
                status, message = "correct", field.correct_feedback
            else:
                status = "try again"
                message = option.feedback if option else field.fallback_feedback
            feedback.append(
                FieldFeedback(
                    label=field.label,
                    value=option.label if option else value,
                    status=status,
                    message=message,
                )
            )
        return PracticeResult(fields=tuple(feedback))


class LessonStage(FrozenRecord):
    """A selected catalogue view with an explicit draft/inspection/acceptance label."""

    id: str
    snapshot: str
    title: str
    status: str
    names: tuple[str, ...]
    fields: tuple[str, ...]
    note: str


class LearningCatalogue(FrozenRecord):
    """Local teaching fixtures, independent of model publication state."""

    practices: tuple[Practice, ...]
    stages: tuple[LessonStage, ...]


def load_learning() -> LearningCatalogue:
    """Load the pinned local exercise and lesson selections."""
    path = Path(__file__).parents[1] / "fixtures" / "learning.json"
    return LearningCatalogue.model_validate_json(path.read_bytes())


def load_practices() -> dict[str, Practice]:
    """Index the authored exercises by stable teaching identity."""
    return {exercise.id: exercise for exercise in load_learning().practices}


def check_learning(*, learning: LearningCatalogue) -> None:
    """Keep selected fields, evidence and answer expectations tied to the shared model."""
    catalogue = load_catalogue()
    passages = {p.id for source in load_sources() for p in source.passages}
    for stage in learning.stages:
        definitions = {d.name: d for d in catalogue.resolve(snapshot=stage.snapshot)}
        if not set(stage.names) <= definitions.keys():
            message = f"Unknown stage definitions: {stage.id}"
            raise ValueError(message)
        fields = {f.name for name in stage.names for f in definitions[name].attributes}
        if not set(stage.fields) <= fields:
            message = f"Unknown stage fields: {stage.id}"
            raise ValueError(message)
    _check_grounded_answers(learning=learning)
    for exercise in learning.practices:
        _check_practice(exercise=exercise, passages=passages)


def _check_practice(*, exercise: Practice, passages: set[str]) -> None:
    """Require a complete, evidence-linked answer and feedback for each alternative."""
    if not exercise.fields or len({f.key for f in exercise.fields}) != len(exercise.fields):
        message = f"Missing or duplicate practice fields: {exercise.id}"
        raise ValueError(message)
    if not set(exercise.evidence) <= passages:
        message = f"Unknown practice evidence: {exercise.id}"
        raise ValueError(message)
    for field in exercise.fields:
        if field.options and field.answer not in {o.value for o in field.options}:
            message = f"Practice answer absent from options: {exercise.id}/{field.key}"
            raise ValueError(message)
        if any(not o.feedback for o in field.options if o.value != field.answer):
            message = f"Missing misconception feedback: {exercise.id}/{field.key}"
            raise ValueError(message)


def _check_grounded_answers(*, learning: LearningCatalogue) -> None:
    """Check the two consumer exercises against the actual published capture contract."""
    catalogue = load_catalogue()
    practices = {e.id: e for e in learning.practices}
    published = {d.name: d for d in catalogue.resolve(snapshot="published")}
    logging = next(
        f for f in published["instructions-for-use"].attributes if f.name == "logging-mechanisms"
    )
    answers = {f.key: f.answer for f in practices["c7-shape"].fields}
    if answers != {
        "presence": "required" if logging.required else "optional",
        "qualification": published["instructions-logging-information"].kind,
    }:
        raise ValueError("Logging practice disagrees with the published field and rule")
    lookup = {f.key: f.answer for f in practices["c7-handoff"].fields}
    if lookup != {
        "field": logging.name,
        "rule": published["instructions-logging-information"].name,
    }:
        raise ValueError("Consumer practice disagrees with the published lookup names")


def render_solution(*, exercise: Practice) -> str:
    """Offer an explicit answer without filling or grading the learner's input."""
    explanations = "".join(
        f"<li><strong>{escape(field.answer)}</strong>: {escape(field.correct_feedback)}</li>"
        for field in exercise.fields
    )
    return (
        f"<h4>Worked answer</h4><ul>{explanations}</ul>"
        f"<pre>{escape(exercise.solution, quote=False)}</pre>"
        f"<p>{escape(exercise.outcome)}</p>"
    )


def render_practice(*, exercise: Practice) -> str:
    """Save the task and expandable answers without relying on widget state."""
    fields = "".join(
        f"<li><strong>{escape(field.label)}</strong>: "
        f"{escape(' / '.join(option.label for option in field.options) or 'Enter a lookup name.')}"
        "</li>"
        for field in exercise.fields
    )
    return (
        '<section class="dk-preview"><div class="dk-eyebrow">HANDS-ON PRACTICE</div>'
        f"<h3>{escape(exercise.title)}</h3><p>{escape(exercise.prompt)}</p><ol>{fields}</ol>"
        f'<p class="dk-note">Evidence: {escape(", ".join(exercise.evidence))}. '
        "Use the controls below, or write down your answers in the reading version.</p>"
        "<details><summary>Worked answer and explanations</summary>"
        f"{render_solution(exercise=exercise)}</details></section>"
    )


def render_feedback(*, exercise: Practice, result: PracticeResult) -> str:
    """Explain every submitted choice and its consequence, without a completion claim."""
    title = "Ready to continue" if result.solved else "Try again"
    panel = Panel(
        title=title,
        columns=("Task", "Your answer", "Feedback"),
        rows=tuple(
            (field.label, field.value or "Unanswered", f"{field.status}: {field.message}")
            for field in result.fields
        ),
        note=exercise.outcome if result.solved else "Revise the indicated answers and check again.",
    )
    return (
        '<div role="status" aria-live="polite">'
        + render_table(panel=panel)
        + "<p>Authored teaching feedback, not SDK validation. No model or review changes.</p></div>"
    )


def render_lesson_stage(*, stage_id: str) -> str:
    """Show only the relevant definitions or fields at this point in the lesson."""
    stage = next(item for item in load_learning().stages if item.id == stage_id)
    definitions = {
        definition.name: definition
        for definition in load_catalogue().resolve(snapshot=stage.snapshot)
    }
    if stage.fields:
        rows = tuple(
            (field.name, f"{field.value_type}; required={field.required}", field.meaning)
            for name in stage.names
            for field in definitions[name].attributes
            if field.name in stage.fields
        )
    else:
        rows = tuple(
            (name, definitions[name].kind, definitions[name].meaning) for name in stage.names
        )
    return (
        '<section class="dk-preview"><div class="dk-eyebrow">SCRIPTED SAMPLE · '
        f"{escape(stage.status)}</div>"
        + render_table(
            panel=Panel(
                title=stage.title,
                columns=("Name", "Shape / kind", "Meaning"),
                rows=rows,
                note=stage.note,
            )
        )
        + "</section>"
    )
