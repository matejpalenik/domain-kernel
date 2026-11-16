from __future__ import annotations

import pytest

MAX_PLANNED_STEP_LINES = 24


def test_prompt_captures_keep_precedence_schema_and_evidence_consistent() -> None:
    from examples.notebooks._preview.discovery import (  # noqa: PLC0415
        check_discovery_lesson,
        load_discovery_lesson,
        render_discovery_example,
    )

    lesson = load_discovery_lesson()
    check_discovery_lesson(lesson=lesson)
    override = next(item for item in lesson.examples if item.id == "override")
    assert override.additional_instructions == lesson.recruitment_focus
    assert override.effective_instructions == lesson.documentation_focus
    assert override.default_prompt_version is None
    assert len({item.source_ids for item in lesson.examples}) == 1
    changed = override.model_copy(update={"effective_instructions": "Wrong merged instructions"})
    with pytest.raises(ValueError, match="Prompt precedence"):
        check_discovery_lesson(lesson=lesson.model_copy(update={"examples": (changed,)}))
    changed = override.model_copy(update={"response_schema_version": "caller-schema"})
    with pytest.raises(ValueError, match="Output contract"):
        check_discovery_lesson(lesson=lesson.model_copy(update={"examples": (changed,)}))
    html = render_discovery_example(example_id="override")
    assert "ignored" in html
    assert "Simulated" in html
    assert "instructions-for-use" in html


def test_discovery_practice_separates_prompt_precedence_from_output_validation() -> None:
    from examples.notebooks._preview.practice import load_practices  # noqa: PLC0415

    exercises = load_practices()
    assert "c4-prompts" in exercises
    exercise = exercises["c4-prompts"]
    wrong = exercise.check(answers={"precedence": "combine", "contract": "accept"})
    assert not wrong.solved
    assert "ignored" in wrong.fields[0].message
    assert "validation" in wrong.fields[1].message
    assert exercise.check(answers={"precedence": "override", "contract": "validate"}).solved


def test_discovery_story_exposes_focus_and_preserves_recoverable_failures() -> None:
    from examples.notebooks._preview.models import load_scenes  # noqa: PLC0415
    from examples.notebooks._preview.validation import FOLDER, Notebook  # noqa: PLC0415

    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    cells = {cell.id: cell.text for cell in notebook.cells}
    assert "additional_instructions=recruitment_focus" in cells["c4-preview"]
    assert "prompt_override=" in cells["c4-override-preview"]
    assert "run.prompt.effective_instructions" in cells["c4-preview"]
    assert "response_schema_json" in cells["c4-prompt-boundary"]
    scene = next(scene for scene in load_scenes() if scene.id == "C4")
    assert "response_schema_invalid" in scene.model_dump_json()
    assert "recover" in {choice.id for choice in scene.choices}


def test_discovery_contract_exposes_both_controls_and_keeps_resume_pinned() -> None:
    import ast  # noqa: PLC0415
    import re  # noqa: PLC0415

    from examples.notebooks._preview.validation import ROOT  # noqa: PLC0415

    blocks = (
        match.group(1)
        for match in re.finditer(
            r"```python\n(.*?)\n```", (ROOT / "INTERFACES.md").read_text(), re.DOTALL
        )
    )
    methods = [
        node
        for block in blocks
        for node in ast.walk(ast.parse(block))
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name in {"discover", "extract_proposals", "resume_discovery"}
    ]
    for method in methods:
        controls = {arg.arg for arg in method.args.kwonlyargs}
        if method.name == "resume_discovery":
            assert not controls & {"additional_instructions", "prompt_override"}
        else:
            assert {"additional_instructions", "prompt_override"} <= controls


def test_practice_feedback_explains_wrong_and_missing_answers() -> None:
    from examples.notebooks._preview.practice import load_practices  # noqa: PLC0415

    exercise = load_practices()["c7-shape"]
    result = exercise.check(answers={"presence": "required", "qualification": "display"})
    assert not result.solved
    assert "universal" in result.fields[0].message
    assert "bundle" in result.fields[1].message
    missing = exercise.check(answers={})
    assert not missing.solved
    assert all(field.status == "unanswered" for field in missing.fields)
    correct = exercise.check(answers={"presence": "optional", "qualification": "rule"})
    assert correct.solved


def test_lookup_practice_checks_names_without_executing_input() -> None:
    from examples.notebooks._preview.practice import load_practices, render_feedback  # noqa: PLC0415

    exercise = load_practices()["c7-handoff"]
    solved = exercise.check(
        answers={"field": " logging-mechanisms ", "rule": "instructions-logging-information"}
    )
    assert solved.solved
    wrong = exercise.check(answers={"field": "<script>raise RuntimeError()</script>"})
    html = render_feedback(exercise=exercise, result=wrong)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "not SDK validation" in html


@pytest.mark.parametrize(
    "identity", ["c4-prompts", "c6-review", "c6-mapping", "c7-shape", "c7-identity", "c7-handoff"]
)
def test_each_practice_has_a_correct_path_and_offline_feedback(identity: str) -> None:
    from examples.notebooks._preview.practice import (  # noqa: PLC0415
        load_practices,
        render_practice,
    )

    exercise = load_practices()[identity]
    result = exercise.check(answers={field.key: field.answer for field in exercise.fields})
    assert result.solved
    assert exercise.outcome
    assert all(field.correct_feedback and field.hint for field in exercise.fields)
    html = render_practice(exercise=exercise)
    assert "Worked answer and explanations" in html
    assert "<details>" in html
    assert exercise.solution.replace("<", "&lt;").replace(">", "&gt;") in html


def test_mapping_exercise_preserves_direction_and_is_not_an_owl_assertion() -> None:
    from examples.notebooks._preview.practice import load_practices  # noqa: PLC0415

    exercise = load_practices()["c6-mapping"]
    wrong = exercise.check(answers={"relation": "broader_than", "effect": "owl"})
    assert not wrong.solved
    assert "reverse" in wrong.fields[0].message
    assert "formal" in wrong.fields[1].message
    assert exercise.check(answers={"relation": "narrower_than", "effect": "mapping"}).solved


def test_learning_fixtures_reject_unknown_fields_and_drifted_answers() -> None:
    from examples.notebooks._preview.practice import (  # noqa: PLC0415
        check_learning,
        load_learning,
    )

    learning = load_learning()
    check_learning(learning=learning)
    stage = next(s for s in learning.stages if s.id == "c7-fields")
    broken = learning.model_copy(
        update={"stages": (stage.model_copy(update={"fields": ("invented-field",)}),)}
    )
    with pytest.raises(ValueError, match="Unknown stage fields"):
        check_learning(learning=broken)
    exercise = next(e for e in learning.practices if e.id == "c7-shape")
    incorrect = exercise.model_copy(
        update={
            "fields": (
                exercise.fields[0].model_copy(update={"answer": "required"}),
                exercise.fields[1],
            )
        }
    )
    broken = learning.model_copy(
        update={
            "practices": tuple(incorrect if e.id == incorrect.id else e for e in learning.practices)
        }
    )
    with pytest.raises(ValueError, match="Logging practice disagrees"):
        check_learning(learning=broken)


def test_c6_c7_are_short_stages_with_separate_review_boundaries() -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415
        FOLDER,
        Notebook,
        planned_code,
    )

    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    cells = {cell.id: cell for cell in notebook.cells}
    for cell in notebook.cells:
        if cell.id.startswith(("c6-", "c7-")) and "PLANNED SDK START" in cell.text:
            block = planned_code(cell=cell)
            assert (
                len([line for line in block.splitlines() if line.strip()]) <= MAX_PLANNED_STEP_LINES
            ), cell.id
    for identity in ("c6-review", "c6-mapping", "c7-shape", "c7-identity", "c7-handoff"):
        assert (
            f'tour.display_practice(exercise_id="{identity}")' in cells[f"{identity}-practice"].text
        )
    order = list(cells)
    assert order.index("c7-add-fields") < order.index("c7-add-rule")
    assert order.index("c7-add-rule") < order.index("c7-repair-key")
    assert order.index("c7-inspect-plan") < order.index("c7-preview")
    assert "decide_review" not in cells["c7-inspect-plan"].text
    assert "preview_changes" not in cells["c7-preview"].text
