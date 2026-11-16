from __future__ import annotations

import subprocess
import sys
from html import escape
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.notebook]
ROOT = Path(__file__).resolve().parents[2]


def test_tour_verifies_live_c1_and_executes_previews_in_a_fresh_offline_kernel() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "examples.notebooks._preview.validation", "--execute"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_widget_callbacks_preserve_review_gates_and_rerun_state() -> None:
    # Import only in the separately provisioned notebook job, not during core collection.
    from examples.notebooks._preview.widgets import get_tour  # noqa: PLC0415

    tour = get_tour()
    branch = tour.get_experiment(chapter="C6")
    view = tour.experiments["C6"]
    view.reset_button.click()
    view.selection.value = "reject"
    view.reason.value = "This suggestion would conflate different actor meanings."
    assert view.submit_button.disabled
    view.preview_button.click()
    assert not view.submit_button.disabled
    view.submit_button.click()
    assert branch.submissions == 1
    assert "unchanged" in str(view.result.value).lower()
    assert tour.get_experiment(chapter="C6") is branch
    assert tour.experiments["C6"] is view
    view.submit_button.click()
    assert branch.submissions == 1
    view.reason.value = "New intent needs another inspection."
    assert view.submit_button.disabled
    view.reason.value = " "
    view.preview_button.click()
    assert "Enter a reason" in str(view.result.value)
    assert view.submit_button.disabled
    view.reset_button.click()
    assert branch.submissions == 0


def test_all_chapter_controls_can_be_constructed_without_source_access() -> None:
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415 -- optional notebook group

    tour = Tour()
    for chapter in tour.scenes:
        branch = tour.get_experiment(chapter=chapter)
        view = tour.experiments[chapter]
        for choice in branch.scene.choices:
            view.selection.value = choice.id
            if choice.interaction == "inspect":
                assert view.submit_button.disabled
                assert "Read-only inspection" in str(view.result.value)
            else:
                view.preview_button.click()
                view.submit_button.click()
            assert escape(choice.after) in str(view.result.value)
        view.reset_button.click()


def test_expanded_inspector_filters_without_mutating_or_replacing_callbacks() -> None:
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415

    tour = Tour()
    original = tour.scenes["C8"].model_dump_json()
    tour.display_inspector(chapter="C8")
    view = tour.models["C8"]
    view.search.value = "instructions"
    view.selection.value = "instructions-for-use"
    assert "Article 13" in str(view.output.value)
    assert "logging-mechanisms" in str(view.output.value)
    view.search.value = "no-such-definition"
    assert "No definitions match" in str(view.output.value)
    view.search.value = "instructions-for-use"
    assert view.selection.value == "instructions-for-use"
    assert "Article 13" in str(view.output.value)
    view.search.value = ""
    view.view_selection.value = "safeguards"
    assert "Data and safeguards" in str(view.graph.value)
    tour.display_inspector(chapter="C8")
    assert tour.models["C8"] is view
    assert tour.scenes["C8"].model_dump_json() == original
    assert not tour.experiments


def test_reading_controls_do_not_apply_decisions_or_lose_selection() -> None:
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415

    tour = Tour()
    original = tour.scenes["C9"].model_dump_json()
    tour.display_consumer()
    view = tour.consumer
    assert view is not None
    view.selection.value = "provider"
    assert "Inferred modelling structure" in str(view.output.value)
    tour.display_consumer()
    assert tour.consumer is view
    assert view.selection.value == "provider"
    tour.display_inspector(chapter="C9")
    model = tour.models["C9"]
    model.presentation.value = "matrix"
    assert "Connection matrix" in str(model.graph.value)
    model.view_selection.value = "safeguards"
    assert "Data and safeguards" in str(model.graph.value)
    model.presentation.value = "diagram"
    assert "<svg" in str(model.graph.value)
    assert not tour.experiments
    assert tour.scenes["C9"].model_dump_json() == original


def test_evolution_selector_preserves_versions_and_does_not_apply_changes() -> None:
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415

    tour = Tour()
    original = {chapter: scene.model_dump_json() for chapter, scene in tour.scenes.items()}
    tour.display_inspector(chapter="C10")
    view = tour.publications["C10"]
    for chapter in ("C2", "C8", "C10"):
        view.selection.value = chapter
        assert tour.scenes[chapter].snapshot in str(view.output.value)
    tour.display_inspector(chapter="C10")
    assert tour.publications["C10"] is view
    assert not tour.experiments
    assert {chapter: scene.model_dump_json() for chapter, scene in tour.scenes.items()} == original


def test_text_edit_sync_preserves_stable_cell_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415
        FOLDER,
        Notebook,
    )

    monkeypatch.setenv("JUPYTER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("JUPYTER_DATA_DIR", str(tmp_path / "data"))
    original = FOLDER / "domain-kernel-tour.ipynb"
    destination = tmp_path / original.name
    _ = destination.write_bytes(original.read_bytes())
    text = (
        original.with_suffix(".py")
        .read_text()
        .replace("# # Domain Kernel Tour", "# # Domain Kernel Tour — sync test", 1)
    )
    _ = destination.with_suffix(".py").write_text(text)
    result = subprocess.run(  # noqa: S603 -- fixed module and pytest-owned temporary path
        [sys.executable, "-m", "jupytext", "--sync", str(destination)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    before = Notebook.model_validate_json(original.read_bytes())
    after = Notebook.model_validate_json(destination.read_bytes())
    assert [cell.id for cell in after.cells] == [cell.id for cell in before.cells]
    assert "sync test" in after.cells[0].text
    assert after.cells[2].outputs


def test_switching_from_reading_to_an_action_uses_its_own_reason() -> None:
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415

    tour = Tour()
    branch = tour.get_experiment(chapter="C3")
    view = tour.experiments["C3"]
    assert branch.choice.interaction == "inspect"
    view.selection.value = "retry"
    assert view.reason.value == branch.choice.reason
    assert view.submit_button.disabled
    view.preview_button.click()
    view.submit_button.click()
    assert branch.submissions == 1
    view.selection.value = "inspect"
    assert "Read-only inspection" in str(view.result.value)
    assert view.submit_button.disabled
    assert branch.submissions == 1
    assert tour.get_experiment(chapter="C3") is branch


def test_practice_controls_check_explicitly_and_preserve_work_on_rerun() -> None:
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415

    tour = Tour()
    originals = {key: scene.model_dump_json() for key, scene in tour.scenes.items()}
    tour.display_practice(exercise_id="c7-shape")
    view = tour.practices["c7-shape"]
    view.check_button.click()
    assert "unanswered" in str(view.feedback.value)
    view.inputs["presence"].value = "required"
    view.inputs["qualification"].value = "display"
    assert "Check your answer" in str(view.feedback.value)
    view.check_button.click()
    assert "Try again" in str(view.feedback.value)
    view.hint_button.click()
    assert "Hint" in str(view.help.value)
    view.solution_button.click()
    assert "Worked answer" in str(view.help.value)
    assert view.inputs["presence"].value == "required"
    view.inputs["presence"].value = "optional"
    view.inputs["qualification"].value = "rule"
    view.check_button.click()
    assert "Ready to continue" in str(view.feedback.value)
    feedback = str(view.feedback.value)
    view.check_button.click()
    assert str(view.feedback.value) == feedback
    tour.display_practice(exercise_id="c7-shape")
    assert tour.practices["c7-shape"] is view
    assert str(view.feedback.value) == feedback
    view.inputs["presence"].value = "required"
    assert "Ready to continue" not in str(view.feedback.value)
    view.reset_button.click()
    assert all(value == "" for value in view.answers.values())
    assert not tour.experiments
    assert {key: scene.model_dump_json() for key, scene in tour.scenes.items()} == originals


def test_every_practice_control_supports_an_explicit_answer_and_reset() -> None:
    from examples.notebooks._preview.practice import load_practices  # noqa: PLC0415
    from examples.notebooks._preview.widgets import Tour  # noqa: PLC0415

    tour = Tour()
    for exercise in load_practices().values():
        tour.display_practice(exercise_id=exercise.id)
        view = tour.practices[exercise.id]
        for field in exercise.fields:
            view.inputs[field.key].value = field.answer
        assert "Ready to continue" not in str(view.feedback.value)
        view.check_button.click()
        assert "Ready to continue" in str(view.feedback.value)
        view.reset_button.click()
        assert all(value == "" for value in view.answers.values())
    assert not tour.experiments
