"""Standard notebook controls over explicitly simulated, in-memory scenes."""

from __future__ import annotations

from functools import cache
from html import escape
from importlib.metadata import version
from pathlib import Path
from platform import python_version
from urllib.parse import urlsplit

import ipywidgets as widgets
from IPython.display import display
from pydantic import TypeAdapter

from examples.notebooks._preview.catalogue import load_sources
from examples.notebooks._preview.discovery import load_discovery_lesson, render_discovery_example
from examples.notebooks._preview.models import Experiment, FrozenRecord, Scene, load_scenes
from examples.notebooks._preview.practice import (
    load_learning,
    load_practices,
    render_lesson_stage,
    render_practice,
)
from examples.notebooks._preview.practice_widgets import PracticeView
from examples.notebooks._preview.rendering import (
    STYLE,
    available_views,
    render_choice,
    render_connection_matrix,
    render_definition,
    render_graph,
    render_snapshot,
    render_text,
)
from examples.notebooks._preview.teaching import (
    render_authoring_stage,
    render_consumer_field,
    render_destination,
    render_requirement_trace,
    render_review_comparison,
)


class Projection(FrozenRecord):
    """An illustrative output excerpt with an explicit compatibility note."""

    name: str
    code: str
    note: str


class ExperimentView:
    """Own one set of callbacks for one persistent in-kernel experiment branch."""

    def __init__(self, *, branch: Experiment) -> None:
        self.branch = branch
        self.selection = widgets.Dropdown(
            options=[(choice.label, choice.id) for choice in branch.scene.choices],
            description="Alternative:",
            layout=widgets.Layout(width="min(100%, 650px)"),
            style={"description_width": "100px"},
        )
        self.reason = widgets.Textarea(
            value=branch.choice.reason,
            description="Reason:",
            layout=widgets.Layout(width="min(100%, 650px)", height="80px"),
            style={"description_width": "100px"},
        )
        self.preview_button = widgets.Button(description="Preview impact", icon="search")
        self.submit_button = widgets.Button(
            description="Apply sample action", button_style="info", disabled=True, icon="check"
        )
        self.reset_button = widgets.Button(description="Reset experiment", icon="undo")
        for button in (self.preview_button, self.submit_button, self.reset_button):
            button.layout = widgets.Layout(width="205px", min_height="36px", margin="4px")
        self.result = widgets.HTML(
            value="<p>Choose an alternative and a reason, then preview its impact. "
            "This branch does not alter the canonical walkthrough above.</p>"
        )
        self.selection.observe(self._changed, names="value")
        self.reason.observe(self._changed, names="value")
        self.preview_button.on_click(self._preview)
        self.submit_button.on_click(self._submit)
        self.reset_button.on_click(self._reset)
        self.widget = widgets.VBox(
            children=[
                widgets.HTML(value="<h3>Try it — separate experiment</h3>"),
                self.selection,
                self.reason,
                widgets.HBox(
                    children=[self.preview_button, self.submit_button, self.reset_button],
                    layout=widgets.Layout(flex_flow="row wrap", grid_gap="8px"),
                ),
                self.result,
            ]
        )
        self.widget.add_class("dk-preview")
        self.widget.add_class("dk-controls")
        self._show_selection()

    def _show_selection(self) -> None:
        """Reading is immediate; only actions expose review controls."""
        inspection = self.branch.choice.interaction == "inspect"
        for control in (self.reason, self.preview_button, self.submit_button):
            control.layout.display = "none" if inspection else ""
        if inspection:
            choice = self.branch.choice
            self.result.value = (
                f"<h4>Read-only inspection</h4><p>{escape(choice.before)}</p>"
                f"<p>{escape(choice.after)}</p><p>{escape(choice.explanation)}</p>"
                "<p>No decision submitted; canonical snapshots are unchanged.</p>"
            )
        else:
            self.result.value = (
                "<p>Choose a reason, preview the impact, then apply the sample action. "
                "This branch does not alter the canonical walkthrough.</p>"
            )

    def _changed(self, _change: dict[str, object]) -> None:
        self.branch.choose(choice_id=str(self.selection.value))
        self.branch.invalidate()
        self.submit_button.disabled = True
        if _change.get("owner") is self.selection:
            self.reason.value = self.branch.choice.reason
        self._show_selection()

    def _preview(self, _button: widgets.Button) -> None:
        try:
            choice = self.branch.preview(reason=str(self.reason.value))
        except ValueError as error:
            self.result.value = f'<p role="alert">{escape(str(error))}</p>'
            self.submit_button.disabled = True
            return
        self.result.value = render_choice(
            choice=choice, reason=self.branch.reason, status=self.branch.status.value
        )
        self.submit_button.disabled = False

    def _submit(self, _button: widgets.Button) -> None:
        self.submit_button.disabled = True
        try:
            self.branch.submit()
        except ValueError as error:
            self.result.value = f'<p role="alert">{escape(str(error))}</p>'
            return
        self.result.value = render_choice(
            choice=self.branch.choice, reason=self.branch.reason, status=self.branch.status.value
        )

    def _reset(self, _button: widgets.Button) -> None:
        self.selection.value = self.branch.scene.choices[0].id
        self.reason.value = self.branch.scene.choices[0].reason
        self.branch.reset()
        self.submit_button.disabled = True
        self._show_selection()


class PublicationView:
    """Select fixed published scenes without creating an experiment or changing history."""

    def __init__(self, *, snapshots: tuple[tuple[str, Scene], ...]) -> None:
        self.selection = widgets.Dropdown(
            options=[(label, scene.id) for label, scene in snapshots],
            value=snapshots[-1][1].id,
            description="Version:",
            layout=widgets.Layout(width="min(100%, 650px)"),
        )
        self.output = widgets.HTML()
        scenes = {scene.id: scene for _label, scene in snapshots}

        def refresh(_change: dict[str, object] | None = None) -> None:
            snapshot = scenes[str(self.selection.value)]
            self.output.value = (
                "<p>Read-only sample publication. Earlier versions remain unchanged; "
                "selecting a version does not publish or approve anything.</p>"
                + render_snapshot(scene=snapshot)
            )

        self.selection.observe(refresh, names="value")
        refresh()
        self.widget = widgets.VBox(children=[self.selection, self.output])


class ModelInspector:
    """Inspect one immutable catalogue snapshot through ordinary keyboard controls."""

    def __init__(self, *, scene: Scene) -> None:
        self.scene = scene
        self.search = widgets.Text(description="Find name:", placeholder="e.g. instructions")
        self.selection = widgets.Dropdown(
            description="Definition:", layout=widgets.Layout(width="min(100%, 750px)")
        )
        self.view_selection = widgets.Dropdown(
            options=[(view.title, view.id) for view in available_views(scene=scene)],
            description="Model view:",
            layout=widgets.Layout(width="min(100%, 750px)"),
        )
        self.output = widgets.HTML()
        self.graph = widgets.HTML()
        self.search_status = widgets.HTML()
        self.presentation = widgets.ToggleButtons(
            options=[("Diagram", "diagram"), ("Connection matrix", "matrix")],
            description="Read as:",
        )
        self.search.observe(self._filter, names="value")
        self.selection.observe(self._refresh, names="value")
        self.view_selection.observe(self._refresh, names="value")
        self.presentation.observe(self._refresh, names="value")
        self._filter()
        if any(item.name == "instructions-for-use" for item in scene.definitions):
            self.selection.value = "instructions-for-use"
            self.view_selection.value = "documentation"
        self.widget = widgets.VBox(
            children=[
                widgets.HTML(
                    value=(
                        "<h3>Explore the model</h3><p>Choose a view or find a definition "
                        "by name. Inspection does not change the model "
                        "or apply a review decision.</p>"
                    )
                ),
                self.view_selection,
                self.presentation,
                self.search,
                self.search_status,
                self.selection,
                self.graph,
                self.output,
            ]
        )

    def _filter(self, _change: dict[str, object] | None = None) -> None:
        query = str(self.search.value).casefold().strip()
        previous = self.selection.value
        options = [
            (item.display_name, item.name)
            for item in self.scene.definitions
            if query in item.name.casefold() or query in item.display_name.casefold()
        ]
        self.selection.options = options
        if previous in {name for _label, name in options}:
            self.selection.value = previous
        elif options:
            self.selection.value = options[0][1]
        self.search_status.value = (
            f"<p role='status'>{len(options)} matching definitions in the complete model.</p>"
            if options
            else "<p role='status'>No definitions match this name. Clear or change the filter.</p>"
        )
        self._refresh()

    def _refresh(self, _change: dict[str, object] | None = None) -> None:
        selected = str(self.selection.value) if self.selection.value is not None else None
        self.graph.value = (
            render_connection_matrix(scene=self.scene, view_id=str(self.view_selection.value))
            if self.presentation.value == "matrix"
            else render_graph(
                scene=self.scene,
                selected=selected,
                view_id=str(self.view_selection.value),
                collapse_table=True,
            )
        )
        definition = next((item for item in self.scene.definitions if item.name == selected), None)
        self.output.value = (
            "<p role='status'>No definitions match this name. "
            "Clear the filter to restore the inventory.</p>"
            if definition is None
            else (
                "<div tabindex='0' role='region' aria-label='Selected definition details' "
                "style='max-height:640px;overflow:auto'>"
                + render_definition(scene=self.scene, definition=definition)
                + "</div>"
            )
        )
        view = next(
            item
            for item in available_views(scene=self.scene)
            if item.id == self.view_selection.value
        )
        if selected is not None and selected not in view.definitions:
            self.graph.value = str(self.graph.value) + (
                "<p class='dk-note'>The selected definition is outside this focused diagram. "
                "Its complete inspection is shown below.</p>"
            )


class ConsumerView:
    """A read-only field selector, never a client or a contract validator."""

    def __init__(self, *, scene: Scene) -> None:
        definition = next(item for item in scene.definitions if item.name == "instructions-for-use")
        self.selection = widgets.Dropdown(
            options=[(field.name, field.name) for field in definition.attributes],
            value="logging-mechanisms",
            description="Field:",
            layout=widgets.Layout(width="min(100%, 650px)"),
        )
        self.output = widgets.HTML()

        def refresh(_change: dict[str, object] | None = None) -> None:
            self.output.value = render_consumer_field(scene=scene, name=str(self.selection.value))

        self.selection.observe(refresh, names="value")
        refresh()
        self.widget = widgets.Accordion(
            children=[widgets.VBox(children=[self.selection, self.output])],
            titles=["Explore another field in the published instructions"],
            selected_index=None,
        )
        self.widget.add_class("dk-preview")
        self.widget.add_class("dk-controls")


class Tour:
    """Load fixed presentation data and cache controls; never impersonate the SDK."""

    def __init__(self) -> None:
        self.scenes = {scene.id: scene for scene in load_scenes()}
        folder = Path(__file__).parents[1] / "fixtures"
        sources = load_sources()
        self.sources = {source.id: source for source in sources}
        self.projections = TypeAdapter(tuple[Projection, ...]).validate_json(
            (folder / "projections.json").read_bytes()
        )
        self.experiments: dict[str, ExperimentView] = {}
        self.inspectors: dict[str, widgets.Widget] = {}
        self.publications: dict[str, PublicationView] = {}
        self.models: dict[str, ModelInspector] = {}
        self.consumer: ConsumerView | None = None
        self.practices: dict[str, PracticeView] = {}

    def display_practice(self, *, exercise_id: str) -> None:
        """Save a static task and reveal cached answer controls without grading on display."""
        if exercise_id not in self.practices:
            self.practices[exercise_id] = PracticeView(exercise=load_practices()[exercise_id])
        view = self.practices[exercise_id]
        display(
            {
                "text/html": STYLE + render_practice(exercise=view.exercise),
                "text/plain": view.exercise.model_dump_json(indent=2),
            },
            raw=True,
        )
        display(view.widget)

    def display_discovery_example(self, *, example_id: str) -> None:
        """Inspect authored prompt captures without running or changing discovery."""
        example = next(item for item in load_discovery_lesson().examples if item.id == example_id)
        display(
            {
                "text/html": STYLE + render_discovery_example(example_id=example_id),
                "text/plain": "Simulated prompt capture: " + example.model_dump_json(indent=2),
            },
            raw=True,
        )

    def display_lesson_stage(self, *, stage_id: str) -> None:
        """Show a bounded stage without advancing the canonical model."""
        stage = next(s for s in load_learning().stages if s.id == stage_id)
        display(
            {
                "text/html": STYLE + render_lesson_stage(stage_id=stage_id),
                "text/plain": stage.model_dump_json(indent=2),
            },
            raw=True,
        )

    def display_destination(self) -> None:
        """Show the final handoff without changing or implying current workspace state."""
        display(
            {
                "text/html": STYLE + render_destination(scene=self.scenes["C9"]),
                "text/plain": "Look ahead at simulated publication 1.1.0: optional logging field "
                "plus the published instructions-logging-information rule and Article 13 evidence.",
            },
            raw=True,
        )

    def display_authoring_stage(self, *, stage: str) -> None:
        """Save each seed-authoring stage independently of later publication output."""
        display(
            {
                "text/html": STYLE + render_authoring_stage(scene=self.scenes["C2"], stage=stage),
                "text/plain": f"Scripted seed stage: {stage}; no publication yet.\n"
                + "\n".join(d.name for d in self.scenes["C2"].definitions),
            },
            raw=True,
        )

    def display_review_comparison(self) -> None:
        """Display inspected meanings without submitting the pending decision."""
        display(
            {
                "text/html": STYLE + render_review_comparison(scene=self.scenes["C6"]),
                "text/plain": "case-007: recruitment purpose is not blanket high-risk equivalence. "
                "Reject preview leaves accepted definitions unchanged; decision not yet submitted.",
            },
            raw=True,
        )

    def display_requirement_trace(self) -> None:
        """Save the complete worked example without a live kernel requirement."""
        scene = self.scenes["C9"]
        display(
            {
                "text/html": STYLE + render_requirement_trace(scene=scene),
                "text/plain": (
                    "Simulated evidence-to-contract journey: Article 13 → proposed document "
                    "merge → case-008 rejects conflation → case-009 adds optional logging "
                    "information → published instructions revision 2 → consumer interpretation.\n"
                    + render_text(scene=scene)
                ),
            },
            raw=True,
        )

    def display_consumer(self) -> None:
        """Show the canonical consumer result and optional cached field exploration."""
        scene = self.scenes["C9"]
        definition = next(item for item in scene.definitions if item.name == "instructions-for-use")
        display(
            {
                "text/html": STYLE + render_consumer_field(scene=scene, name="logging-mechanisms"),
                "text/plain": "Read-only simulated consumer inspection\n"
                + definition.model_dump_json(indent=2),
            },
            raw=True,
        )
        if self.consumer is None:
            self.consumer = ConsumerView(scene=scene)
        display(self.consumer.widget)

    def get_snapshot(self, *, chapter: str) -> Scene:
        """Return a frozen canonical snapshot; this does not execute SDK behavior."""
        return self.scenes[chapter]

    def get_experiment(self, *, chapter: str) -> Experiment:
        """Keep the same branch and callback set across cell reruns."""
        if chapter not in self.experiments:
            self.experiments[chapter] = ExperimentView(
                branch=Experiment(scene=self.get_snapshot(chapter=chapter))
            )
        return self.experiments[chapter].branch

    def display_snapshot(self, *, snapshot: Scene) -> None:
        """Display rich and plain-text representations of already-loaded data."""
        display(
            {
                "text/html": render_snapshot(scene=snapshot),
                "text/plain": render_text(scene=snapshot),
            },
            raw=True,
        )

    def display_definition(self, *, chapter: str, name: str) -> None:
        """Save an inspected canonical definition as ordinary HTML and text output."""
        scene = self.scenes[chapter]
        definition = next(item for item in scene.definitions if item.name == name)
        html = (
            STYLE
            + '<section class="dk-preview">'
            + render_definition(scene=scene, definition=definition)
            + "</section>"
        )
        display({"text/html": html, "text/plain": definition.model_dump_json(indent=2)}, raw=True)

    def display_proposal(self, *, name: str) -> None:
        """Show a curated discovery proposal without changing the accepted model."""
        scene = self.scenes["C6"].model_copy(update={"reviews": (), "mappings": ()})
        definition = next(item for item in scene.definitions if item.name == name)
        html = (
            STYLE
            + '<section class="dk-preview">'
            + render_definition(
                scene=scene,
                definition=definition,
                status="Pending discovery proposal — not accepted in C4",
            )
            + "</section>"
        )
        display(
            {
                "text/html": html,
                "text/plain": "Pending proposal\n" + definition.model_dump_json(indent=2),
            },
            raw=True,
        )

    def display_experiment(self, *, chapter: str) -> None:
        """Display cached controls without applying an action or resetting state."""
        self.get_experiment(chapter=chapter)
        display(self.experiments[chapter].widget)

    def display_environment(self) -> None:
        """Show actual kernel/tool versions beside the simulated capability boundary."""
        packages = ("domain-kernel", "ipywidgets", "ipykernel", "jupytext")
        rows = "".join(
            f"<tr><td>{escape(name)}</td><td>{escape(version(name))}</td></tr>" for name in packages
        )
        html = (
            STYLE
            + '<section class="dk-preview"><div class="dk-eyebrow">INTERACTIVE PREVIEW</div>'
            + '<h2>From dense sources to shared meaning</h2><p class="dk-lead">'
            + "Build a reusable legislative model for AI in recruitment. Explore the planned SDK "
            + "through a complete sample journey, then try alternatives "
            + "in separate experiments.</p>"
            + '<div class="dk-callout"><strong>Interactive preview — simulated SDK results</strong>'
            + "<br>Source references are real and acquisition status is explicit. "
            + "Parsing, inference, "
            + "review, persistence, publication and exports are simulated. No credentials or live "
            + "services are used.</div>"
            + f"<h3>Actual environment</h3><p>Python {escape(python_version())}</p>"
            + '<table><thead><tr><th scope="col">Package</th><th scope="col">Installed version</th>'
            + f"</tr></thead><tbody>{rows}</tbody></table>"
            + '<p class="dk-note">21 chapters and exercises · 43 roadmap owners · '
            + "Preview success never marks an SDK capability complete.</p></section>"
        )
        display(
            {"text/html": html, "text/plain": "Interactive preview — simulated SDK results"},
            raw=True,
        )

    def display_inspector(self, *, chapter: str) -> None:
        """Expose optional selectors over the current chapter's loaded fixtures."""
        if chapter not in self.inspectors:
            scene = self.get_snapshot(chapter=chapter)
            children: list[widgets.Widget] = []
            titles: list[str] = []
            if scene.sources:
                children.append(self._evidence_inspector(scene=scene))
                titles.append("Inspect a source passage")
            if scene.nodes:
                children.append(self._model_inspector(scene=scene))
                titles.append("Explore the model: views, definitions and connections")
            if chapter in {"C9", "E8", "R1"}:
                children.append(self._projection_inspector())
                titles.append("Compare the curated export formats")
            if chapter == "C10":
                children.append(self._evolution_inspector())
                titles.append("Compare immutable publications")
            inspector = widgets.Accordion(children=children, titles=titles, selected_index=None)
            inspector.add_class("dk-preview")
            inspector.add_class("dk-controls")
            self.inspectors[chapter] = inspector
        display(self.inspectors[chapter])

    def _evidence_inspector(self, *, scene: Scene) -> widgets.Widget:
        entries = [
            (self.sources[key], passage)
            for key in scene.sources
            for passage in self.sources[key].passages
        ]
        selector = widgets.Dropdown(
            options=[
                (f"{source.title} · {passage.locator}", index)
                for index, (source, passage) in enumerate(entries)
            ],
            description="Evidence:",
            layout=widgets.Layout(width="min(100%, 850px)"),
        )
        output = widgets.HTML()

        def refresh(_change: dict[str, object] | None = None) -> None:
            source, passage = entries[int(selector.value)]
            url = source.url if urlsplit(source.url).scheme in {"http", "https"} else ""
            link = (
                f'<a href="{escape(url, quote=True)}" target="_blank" '
                'rel="noopener noreferrer">Open original source</a>'
                if url
                else "No source link"
            )
            output.value = (
                STYLE
                + '<section class="dk-preview"><div class="dk-eyebrow">'
                + "EXPLICIT EVIDENCE INSPECTION</div>"
                + f"<h3>{escape(source.title)}</h3><p>{escape(source.classification)} · "
                + f"{escape(source.edition)}</p>"
                + f'<span class="dk-badge">{escape(passage.kind)}</span>'
                + f"<p>{escape(passage.text)}</p>"
                + f"<p><strong>Location:</strong> {escape(passage.locator)}</p>"
                + f"<p><strong>Verification:</strong> {escape(source.verification)}</p>"
                + '<p class="dk-note">SHA-256 of acquired original: '
                + escape(source.sha256 or "Not acquired — no hash claimed")
                + "</p>"
                + f'<p class="dk-note">{escape(source.attribution)}</p>{link}</section>'
            )

        selector.observe(refresh, names="value")
        refresh()
        return widgets.VBox(children=[selector, output])

    def _model_inspector(self, *, scene: Scene) -> widgets.Widget:
        if scene.definitions:
            view = ModelInspector(scene=scene)
            self.models[scene.id] = view
            return view.widget
        selector = widgets.Dropdown(
            options=[("All definitions", "")] + [(node.label, node.id) for node in scene.nodes],
            description="Highlight:",
            layout=widgets.Layout(width="min(100%, 600px)"),
        )
        output = widgets.HTML()

        def refresh(_change: dict[str, object] | None = None) -> None:
            output.value = render_snapshot(scene=scene, selected=str(selector.value) or None)

        selector.observe(refresh, names="value")
        refresh()
        accordion = widgets.Accordion(children=[widgets.VBox(children=[selector, output])])
        accordion.set_title(
            0, "Explore the model — select a definition to highlight its relationships"
        )
        accordion.selected_index = None
        return accordion

    def _projection_inspector(self) -> widgets.Widget:
        selector = widgets.Dropdown(
            options=[(projection.name, index) for index, projection in enumerate(self.projections)],
            description="Format:",
        )
        output = widgets.HTML()

        def refresh(_change: dict[str, object] | None = None) -> None:
            projection = self.projections[int(selector.value)]
            output.value = (
                STYLE
                + '<section class="dk-preview"><div class="dk-eyebrow">'
                + "ILLUSTRATIVE OUTPUT EXCERPT</div>"
                + f"<h3>{escape(projection.name)}</h3><pre>{escape(projection.code)}</pre>"
                + f'<p class="dk-note">{escape(projection.note)}</p></section>'
            )

        selector.observe(refresh, names="value")
        refresh()
        return widgets.VBox(children=[selector, output])

    def _evolution_inspector(self) -> widgets.Widget:
        view = PublicationView(
            snapshots=(
                ("1.0.0 · first publication", self.scenes["C2"]),
                ("1.1.0 · reconciled model", self.scenes["C8"]),
                ("1.2.0 · additional stakeholder evidence", self.scenes["C10"]),
            )
        )
        self.publications["C10"] = view
        return view.widget


@cache
def get_tour() -> Tour:
    """Reuse this kernel's preview state; restarting the kernel rebuilds fixtures."""
    return Tour()
