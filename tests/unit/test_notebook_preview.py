from __future__ import annotations

from pathlib import Path
from re import finditer

import pytest

from examples.notebooks._preview.models import Experiment, ExperimentStatus, load_scenes
from examples.notebooks._preview.rendering import render_snapshot


def test_kernel_restart_signature_preserves_bytes_across_stream_frames() -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415 -- checker-specific test
        restart_signature,
    )

    combined = [{"output_type": "stream", "name": "stdout", "text": "model sha256:bundle\n"}]
    split = [
        {"output_type": "stream", "name": "stdout", "text": "model "},
        {"output_type": "stream", "name": "stderr", "text": "Kernel diagnostic"},
        {"output_type": "stream", "name": "stdout", "text": ["sha256:", "bundle\n"]},
    ]
    assert restart_signature(outputs=combined) == restart_signature(outputs=split)
    split[-1]["text"] = "sha256:changed\n"
    assert restart_signature(outputs=combined) != restart_signature(outputs=split)


def test_all_chapters_have_owned_executable_preview_content() -> None:
    scenes = load_scenes()
    assert tuple(scene.id for scene in scenes) == (
        *(f"C{number}" for number in range(1, 11)),
        *(f"E{number}" for number in range(1, 11)),
        "R1",
    )
    assert {owner for scene in scenes for owner in scene.owners} == {
        f"DK-{number:03}" for number in range(1, 44)
    }
    for scene in scenes:
        assert scene.panels
        assert scene.choices
        assert scene.expected
        assert len({choice.id for choice in scene.choices}) == len(scene.choices)


def test_expanded_model_is_visible_without_promoting_pending_discovery() -> None:
    scenes = {scene.id: scene for scene in load_scenes()}
    assert len(scenes["C8"].nodes) > len(scenes["C2"].nodes)
    assert scenes["C4"].nodes == scenes["C2"].nodes
    for name in ("instructions-for-use", "technical-documentation", "oversight-assignment"):
        assert name in {node.id for node in scenes["C8"].nodes}


def test_static_publication_explains_qualifications_and_complete_inventory() -> None:
    scene = next(scene for scene in load_scenes() if scene.id == "C8")
    html = render_snapshot(scene=scene)
    assert "Complete definition inventory" in html
    assert "under their control" in html
    assert "Article 6(3)" in html
    assert "Instructions for use" in html


def test_canonical_graph_changes_only_after_review_and_preserves_prior_definitions() -> None:
    scenes = {scene.id: scene for scene in load_scenes()}
    # Discovery proposes additions; it cannot put them in the accepted model yet.
    assert scenes["C4"].nodes == scenes["C2"].nodes
    assert scenes["C4"].edges == scenes["C2"].edges
    assert {node.id for node in scenes["C2"].nodes} < {node.id for node in scenes["C6"].nodes}
    assert {"instructions-for-use", "technical-documentation", "dataset"} <= {
        node.id for node in scenes["C6"].nodes
    }
    assert {edge.label for edge in scenes["C2"].edges} < {edge.label for edge in scenes["C6"].edges}
    # Additional stakeholder evidence extends the model without rewriting its meanings.
    assert set(scenes["C8"].nodes) < set(scenes["C10"].nodes)
    assert set(scenes["C8"].edges) < set(scenes["C10"].edges)


def test_submission_requires_inspection_and_reject_does_not_change_baseline() -> None:
    scene = next(scene for scene in load_scenes() if scene.id == "C6")
    branch = Experiment(scene=scene)
    before = scene.model_dump_json()
    with pytest.raises(ValueError, match="Preview"):
        _ = branch.submit()
    branch.choose(choice_id="reject")
    _ = branch.preview(reason="Keep the narrower recruitment meaning.")
    result = branch.submit()
    assert "unchanged" in result.lower()
    assert branch.submissions == 1
    assert branch.submit() == result
    assert branch.submissions == 1
    assert scene.model_dump_json() == before


def test_changing_a_decision_invalidates_the_inspected_preview() -> None:
    scene = next(scene for scene in load_scenes() if scene.id == "C6")
    branch = Experiment(scene=scene)
    _ = branch.preview(reason="Inspect the proposed mapping.")
    branch.choose(choice_id="correct")
    with pytest.raises(ValueError, match="Preview"):
        _ = branch.submit()
    assert branch.submissions == 0


def test_blocker_can_be_repaired_only_in_the_experiment() -> None:
    scene = next(scene for scene in load_scenes() if scene.id == "C8")
    branch = Experiment(scene=scene)
    branch.choose(choice_id="blocked")
    _ = branch.preview(reason="Try the defective candidate.")
    _ = branch.submit()
    assert branch.status is ExperimentStatus.BLOCKED
    branch.choose(choice_id="repair")
    _ = branch.preview(reason="Restore the unresolved relationship endpoint.")
    _ = branch.submit()
    assert branch.status is ExperimentStatus.APPLIED
    assert branch.submissions == 1
    assert scene.snapshot == "recruitment-1.1.0"
    branch.reset()
    assert branch.status is ExperimentStatus.DRAFT
    assert branch.submissions == 0


def test_blank_reason_is_not_a_review() -> None:
    branch = Experiment(scene=load_scenes()[0])
    with pytest.raises(ValueError, match="reason"):
        _ = branch.preview(reason="  ")


def test_rendering_escapes_source_content_and_has_accessible_graph_table() -> None:
    scene = next(scene for scene in load_scenes() if scene.id == "C2")
    changed = scene.model_copy(update={"title": "<script>alert('source')</script>"})
    html = render_snapshot(scene=changed, selected="ai-system")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<svg" in html
    assert "<table" in html
    assert "Simulated SDK result" in html
    assert "AI provider" in html


def test_saved_artifacts_do_not_depend_on_a_previous_widget_kernel() -> None:
    root = Path(__file__).parents[2] / "examples" / "notebooks"
    notebook = (root / "domain-kernel-tour.ipynb").read_text()
    reading = (root / "domain-kernel-tour.html").read_text()
    assert (root / "domain-kernel-tour.py").is_file()
    assert (root / "coverage.json").is_file()
    assert "application/vnd.jupyter.widget-state+json" not in notebook
    assert "application/vnd.jupyter.widget-view+json" not in notebook
    assert "<script" not in reading.lower()
    assert "<svg" in reading
    assert "<table" in reading


def test_coverage_rejects_missing_cells_and_changed_fixture_pins() -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415 -- checker-specific test
        FOLDER,
        Coverage,
        Notebook,
        check_coverage,
    )

    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    coverage = Coverage.model_validate_json((FOLDER / "coverage.json").read_bytes())
    incomplete = notebook.model_copy(
        update={"cells": [cell for cell in notebook.cells if cell.id != "c6-preview"]}
    )
    with pytest.raises(ValueError, match="Missing or unstable cell"):
        check_coverage(notebook=incomplete, coverage=coverage)
    changed = coverage.model_copy(update={"fixture_hashes": {"fixtures/scenes.json": "invalid"}})
    with pytest.raises(ValueError, match="Fixture pin changed"):
        check_coverage(notebook=notebook, coverage=changed)


def test_partial_notebook_coverage_requires_sdk_evidence() -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415 -- checker-specific test
        FOLDER,
        Coverage,
        Notebook,
        check_coverage,
    )

    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    coverage = Coverage.model_validate_json((FOLDER / "coverage.json").read_bytes())
    c1, *later = coverage.chapters
    partial = c1.model_copy(update={"sdk_status": "partial", "sdk_contributions": {}})
    incomplete = coverage.model_copy(update={"chapters": [partial, *later]})

    with pytest.raises(ValueError, match="SDK evidence"):
        check_coverage(notebook=notebook, coverage=incomplete)


@pytest.mark.parametrize(
    ("update", "error"),
    [
        ({"source": "# Future SDK operation"}, "Missing executable SDK cell"),
        ({"outputs": []}, "Missing expected SDK output"),
    ],
)
def test_sdk_coverage_requires_executable_cells_and_observed_output(
    update: dict[str, object], error: str
) -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415 -- checker-specific test
        FOLDER,
        Coverage,
        Notebook,
        check_coverage,
    )

    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    coverage = Coverage.model_validate_json((FOLDER / "coverage.json").read_bytes())
    notebook.cells = [
        cell.model_copy(update=update) if cell.id == "c1-sdk-scope" else cell
        for cell in notebook.cells
    ]

    with pytest.raises(ValueError, match=error):
        check_coverage(notebook=notebook, coverage=coverage)


def test_planned_keyword_check_rejects_undocumented_arguments() -> None:
    from examples.notebooks._preview.validation import (  # noqa: PLC0415 -- checker-specific test
        Cell,
        CellMetadata,
        Notebook,
        check_planned_calls,
    )

    cell = Cell(
        id="invalid-planned-call",
        cell_type="code",
        metadata=CellMetadata(tour_id="invalid-planned-call"),
        source=(
            "# --- PLANNED SDK START ---\n"
            "# await model.publish(undocumented_argument=True)\n"
            "# --- PLANNED SDK END ---"
        ),
    )
    with pytest.raises(ValueError, match="Undocumented keywords"):
        check_planned_calls(notebook=Notebook(cells=[cell]))


def test_grounded_distinctions_survive_publication_and_stakeholder_evidence() -> None:
    from examples.notebooks._preview.catalogue import load_catalogue  # noqa: PLC0415

    catalogue = load_catalogue()
    published = {item.name: item for item in catalogue.resolve(snapshot="published")}
    evolved = {item.name: item for item in catalogue.resolve(snapshot="evolved")}
    assert all(evolved[name] == definition for name, definition in published.items())
    assert {"stakeholder-position", "concerns"} == set(evolved) - set(published)
    assert published["recruitment-ai-system"].id != published["ai-system"].id
    assert published["instructions-for-use"].id != published["technical-documentation"].id
    classification = published["classification-decision"].model_dump_json()
    assert "profiling" in classification
    assert "qualification" in classification
    assert "Unresolved interpretation" in classification
    assert "input data under deployer control" in published["dataset-responsibility"].meaning
    retention = published["deployer-log-retention"].model_dump_json()
    for qualification in ("under their control", "six months", "national law", "not converted"):
        assert qualification in retention
    snapshot = next(item for item in catalogue.snapshots if item.id == "published")
    blanket = next(
        mapping
        for mapping in snapshot.mappings
        if mapping.definition == "recruitment-ai-system" and mapping.relation == "same_as"
    )
    assert blanket.decision == "rejected"


def test_manual_judgement_is_not_a_machine_pass_or_silent_policy_change() -> None:
    from examples.notebooks._preview.catalogue import load_catalogue  # noqa: PLC0415

    catalogue = load_catalogue()
    before = next(
        item
        for item in catalogue.resolve(snapshot="refined")
        if item.name == "classification-scope-review"
    )
    after = next(
        item for item in catalogue.resolve(snapshot="published") if item.name == before.name
    )
    assert before.id == after.id
    assert after == before
    assert dict(before.details)["Requirement"] == "advisory"
    assert "unknown" in dict(before.details)["Machine outcome"]
    assert "never converted" in dict(after.details)["Machine outcome"]
    refined = {d.name for d in catalogue.resolve(snapshot="refined")}
    published = {d.name for d in catalogue.resolve(snapshot="published")}
    assert published - refined == {"instructions-describe-system"}
    assert any(
        before.name in review.targets and review.reason
        for review in catalogue.reviews
        if review.id == "case-010"
    )


def test_catalogue_checks_reject_broken_evidence_and_relationships() -> None:
    from examples.notebooks._preview.catalogue import load_catalogue, load_sources  # noqa: PLC0415
    from examples.notebooks._preview.consistency import check_catalogue  # noqa: PLC0415

    catalogue = load_catalogue()
    sources = load_sources()
    missing_evidence = catalogue.definitions[0].model_copy(update={"evidence": ("missing",)})
    broken = catalogue.model_copy(
        update={"definitions": (missing_evidence, *catalogue.definitions[1:])}
    )
    with pytest.raises(ValueError, match="Unknown evidence"):
        check_catalogue(catalogue=broken, sources=sources)
    definitions = tuple(
        item.model_copy(update={"target": "missing"}) if item.kind == "relationship" else item
        for item in catalogue.definitions
    )
    with pytest.raises(ValueError, match="Invalid relationship endpoint"):
        check_catalogue(
            catalogue=catalogue.model_copy(update={"definitions": definitions}), sources=sources
        )


def test_every_definition_is_available_beyond_the_focused_diagrams() -> None:
    from examples.notebooks._preview.consistency import MAX_VIEW_NODES  # noqa: PLC0415
    from examples.notebooks._preview.rendering import available_views  # noqa: PLC0415

    scene = next(scene for scene in load_scenes() if scene.id == "C8")
    html = render_snapshot(scene=scene)
    for definition in scene.definitions:
        assert definition.name in html
    views = available_views(scene=scene)
    assert {view.id for view in views} == {
        "recruitment",
        "actors",
        "documentation",
        "safeguards",
        "sources",
    }
    assert all(len(view.definitions) <= MAX_VIEW_NODES for view in views)


def test_article_13_trace_preserves_rejection_and_conditional_field() -> None:
    from examples.notebooks._preview.teaching import render_requirement_trace  # noqa: PLC0415

    scenes = {scene.id: scene for scene in load_scenes()}
    html = render_requirement_trace(scene=scenes["C9"])
    for fact in (
        "ai-13-instructions",
        "case-008",
        "case-009",
        "logging-mechanisms",
        "technical-documentation",
        "Where relevant",
        "optional",
        "revision 2",
    ):
        assert fact in html
    assert "Rejected" in html
    assert "Simulated" in html
    assert "not an SDK exporter" in html


def test_consumer_inspection_uses_only_the_selected_publication() -> None:
    from examples.notebooks._preview.teaching import render_consumer_field  # noqa: PLC0415

    scene = next(scene for scene in load_scenes() if scene.id == "C9")
    before = scene.model_dump_json()
    html = render_consumer_field(scene=scene, name="logging-mechanisms")
    assert "ifu-logging-mechanisms" in html
    assert "Where relevant" in html
    assert "does not establish legal completeness" in html
    assert "Article 13" in html
    provider = render_consumer_field(scene=scene, name="provider")
    assert "Inferred modelling structure" in provider
    assert scene.model_dump_json() == before
    with pytest.raises(ValueError, match="Unknown instructions field"):
        _ = render_consumer_field(scene=scene, name="missing")


def test_discovery_focus_precedes_accepted_model_and_keeps_details_available() -> None:
    scene = next(scene for scene in load_scenes() if scene.id == "C4")
    html = render_snapshot(scene=scene)
    assert html.index("Pending proposal groups") < html.index("<svg")
    assert "Inspect supporting detail" in html
    assert "Discovery inspection" in html


def test_connection_matrix_preserves_directed_edge_roles() -> None:
    from examples.notebooks._preview.rendering import render_connection_matrix  # noqa: PLC0415

    scene = next(scene for scene in load_scenes() if scene.id == "C8")
    html = render_connection_matrix(scene=scene, view_id="documentation")
    assert "Rows are sources" in html
    assert "domain relationship" in html
    assert "attribute reference" in html
    assert "Instructions for use" in html
    assert "Technical documentation" in html
    assert 'scope="row"' in html


def test_focused_graph_connection_numbers_remain_distinguishable() -> None:
    from examples.notebooks._preview.rendering import available_views, render_graph  # noqa: PLC0415

    scene = next(scene for scene in load_scenes() if scene.id == "C8")
    for view in available_views(scene=scene):
        html = render_graph(scene=scene, view_id=view.id)
        labels = [
            (float(match.group(1)), float(match.group(2)))
            for match in finditer(r'<circle cx="([^"]+)" cy="([^"]+)"', html)
        ]
        for index, (x, y) in enumerate(labels):
            assert all((x - a) ** 2 + (y - b) ** 2 >= 30**2 for a, b in labels[:index])


def test_read_only_choices_cannot_create_decisions() -> None:
    for scene in load_scenes():
        for choice in scene.choices:
            if choice.interaction != "inspect":
                continue
            branch = Experiment(scene=scene)
            branch.choose(choice_id=choice.id)
            with pytest.raises(ValueError, match="read-only"):
                _ = branch.preview(reason="Inspection needs no reason.")
            with pytest.raises(ValueError, match="Read-only"):
                _ = branch.submit()
            assert branch.submissions == 0
            assert branch.status is ExperimentStatus.DRAFT


@pytest.mark.parametrize(
    ("chapter", "choice_id", "broken_result", "message"),
    [
        ("C2", "accept", "case-001 accepted; pub-001 created", "C2 experiment"),
        ("C9", "supported", "provision.schema.json; compound key k005-1", "C9 experiment"),
        ("C10", "extend", "case-010; 6 concepts, 5 relationships", "C10 experiment"),
        ("E7", "inspect", "evt-start → act-inspect → evt-end", "E7 experiment"),
        ("E8", "import", "Import LegalProvision; accepted additions=0", "E8 experiment"),
        ("E9", "resume", "Resume extraction-02; case-008 added", "E9 experiment"),
    ],
)
def test_experiment_checks_reject_previous_misleading_results(
    chapter: str, choice_id: str, broken_result: str, message: str
) -> None:
    from examples.notebooks._preview.catalogue import load_catalogue  # noqa: PLC0415
    from examples.notebooks._preview.consistency import check_experiment_examples  # noqa: PLC0415

    scenes = load_scenes()
    check_experiment_examples(scenes=scenes, catalogue=load_catalogue())
    broken = tuple(
        scene.model_copy(
            update={
                "choices": tuple(
                    choice.model_copy(update={"after": broken_result})
                    if choice.id == choice_id
                    else choice
                    for choice in scene.choices
                )
            }
        )
        if scene.id == chapter
        else scene
        for scene in scenes
    )
    with pytest.raises(ValueError, match=message):
        check_experiment_examples(scenes=broken, catalogue=load_catalogue())


def test_logging_condition_is_a_reviewed_definition_not_only_a_display_annotation() -> None:
    from examples.notebooks._preview.catalogue import load_catalogue  # noqa: PLC0415
    from examples.notebooks._preview.teaching import render_consumer_field  # noqa: PLC0415

    catalogue = load_catalogue()
    name = "instructions-logging-information"
    assert name not in {d.name for d in catalogue.resolve(snapshot="reconciled")}
    published = {d.name: d for d in catalogue.resolve(snapshot="published")}
    rule = published[name]
    assert rule.kind == "rule"
    assert "Where relevant" in rule.meaning
    assert "ai-13-instructions" in rule.evidence
    assert any(name in r.targets and r.action == "accept" for r in catalogue.reviews)
    scene = next(s for s in load_scenes() if s.id == "C9")
    html = render_consumer_field(scene=scene, name="logging-mechanisms")
    assert name in html
    assert rule.meaning in html
    assert "Teaching commentary" in html


def test_first_journey_teaches_stages_and_checks_without_positional_case_selection() -> None:
    from examples.notebooks._preview.validation import FOLDER, Notebook  # noqa: PLC0415

    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    cells = {cell.id: cell for cell in notebook.cells}
    identities = list(cells)
    assert identities.index("tour-destination-preview") < identities.index("c1-introduction")
    assert identities.index("c2-author") < identities.index("c2-impact")
    assert identities.index("c2-impact") < identities.index("c2-decision")
    assert identities.index("c2-decision") < identities.index("c2-preview")
    assert identities.index("tour-completion") < identities.index("advanced-introduction")
    for number in range(1, 11):
        assert "Reveal the explanation" in cells[f"c{number}-checkpoint"].text
    assert "pending.items[" not in cells["c6-inspect-cases"].text
    assert "pending_update.items[" not in cells["c10-preview"].text
    assert 'ReviewCaseId(value="case-012")' in cells["c10-preview"].text
    assert "edit_definition" not in cells["c8-preview"].text
    assert "add_relationship" in cells["c8-preview"].text
    assert "display name" in cells["c7-experiment"].text
    assert "Edit an attribute meaning" not in cells["c7-experiment"].text
