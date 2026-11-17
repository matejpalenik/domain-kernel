"""Check tour coverage and optionally execute or rebuild the reading outputs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from examples.notebooks._preview.catalogue import load_catalogue, load_sources
from examples.notebooks._preview.consistency import (
    MAX_VIEW_NODES,
    check_catalogue,
    check_experiment_examples,
    check_projection_examples,
)
from examples.notebooks._preview.discovery import check_discovery_lesson, load_discovery_lesson
from examples.notebooks._preview.models import Scene, load_scenes
from examples.notebooks._preview.practice import check_learning, load_learning
from examples.notebooks._preview.rendering import available_views

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT / "examples" / "notebooks"


class CellMetadata(BaseModel):
    """Only the metadata needed by the coverage checker."""

    tour_id: str
    tags: list[str] = Field(default_factory=list)


class Cell(BaseModel):
    """Typed read boundary for the notebook JSON."""

    id: str
    cell_type: Literal["code", "markdown", "raw"]
    source: str | list[str]
    metadata: CellMetadata
    outputs: list[dict[str, object]] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Normalize on-disk line arrays and in-memory cell strings."""
        return self.source if isinstance(self.source, str) else "".join(self.source)


class Notebook(BaseModel):
    """The cells are the common contract between both paired representations."""

    cells: list[Cell]


class SourcePin(BaseModel):
    """Identify a source edition used by an SDK step."""

    source_id: str
    sha256: str


class SDKContribution(BaseModel):
    """Acceptance evidence for an executable SDK step in the tour."""

    cell_id: str
    expected_stdout: str
    automated_checks: list[str]
    source_pin: SourcePin | None = None


class CoverageEntry(BaseModel):
    """Keep simulated preview evidence distinct from SDK execution evidence."""

    chapter: str
    notebook: str
    cell_ids: list[str]
    owners: list[str]
    snapshot: str
    source_ids: list[str]
    preview_status: Literal["implemented", "replaced"]
    sdk_status: Literal["planned", "partial"]
    sdk_contributions: dict[str, SDKContribution | list[SDKContribution]] = Field(
        default_factory=dict
    )
    expected_outcome: str
    automated_checks: list[str]
    human_acceptance: str
    expected_definitions: list[str] = Field(default_factory=list)
    source_passages: list[str] = Field(default_factory=list)

    def contributions(self) -> Iterator[tuple[str, SDKContribution]]:
        """Visit each executable step for this section's contributing tickets."""
        for owner, steps in self.sdk_contributions.items():
            for step in steps if isinstance(steps, list) else (steps,):
                yield owner, step


class Coverage(BaseModel):
    """Versioned ledger for the canonical tour."""

    schema_version: Literal[1]
    fixture_hashes: dict[str, str]
    chapters: list[CoverageEntry]


def planned_code(*, cell: Cell) -> str:
    """Recover intentionally commented planned Python without executing it."""
    start = "# --- PLANNED SDK START ---\n"
    end = "# --- PLANNED SDK END ---"
    if start not in cell.text or end not in cell.text:
        message = f"Missing planned SDK block in {cell.id}"
        raise ValueError(message)
    block = cell.text.split(start, 1)[1].split(end, 1)[0]
    lines = block.splitlines()
    if any(not line.startswith("#") for line in lines):
        message = f"A planned SDK block is executable in {cell.id}"
        raise ValueError(message)
    return "\n".join(line[2:] if line.startswith("# ") else "" for line in lines)


def _class_fields(*, node: ast.ClassDef) -> set[str]:
    init = next(
        (
            item
            for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "__init__"
        ),
        None,
    )
    if init is not None:
        return {arg.arg for arg in (*init.args.args, *init.args.kwonlyargs)} - {"self"}
    return {
        item.target.id
        for item in node.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    }


def _inherit_fields(
    *, name: str, classes: dict[str, ast.ClassDef], seen: frozenset[str] = frozenset()
) -> set[str]:
    if name in seen or name not in classes:
        return set()
    node = classes[name]
    fields = _class_fields(node=node)
    for base in node.bases:
        if isinstance(base, ast.Name):
            fields.update(_inherit_fields(name=base.id, classes=classes, seen=seen | {name}))
    return fields


def _documented_keywords() -> dict[str, list[set[str]]]:
    signatures: dict[str, list[set[str]]] = {}
    classes: dict[str, ast.ClassDef] = {}
    blocks = re.findall(r"```python\n(.*?)\n```", (ROOT / "INTERFACES.md").read_text(), re.DOTALL)
    for block in blocks:
        for node in ast.walk(ast.parse(block)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.args.kwarg is None:
                    keywords = {arg.arg for arg in (*node.args.args, *node.args.kwonlyargs)}
                    signatures.setdefault(node.name, []).append(keywords - {"self", "cls"})
            elif isinstance(node, ast.ClassDef):
                classes[node.name] = node
    # Pydantic source descriptors inherit fields such as FileSource.location.
    for name in classes:
        fields = _inherit_fields(name=name, classes=classes)
        if fields:
            signatures[name] = [fields]
    return signatures


def check_planned_calls(*, notebook: Notebook) -> None:
    """Check syntax and keyword names against documented contracts, not runtime availability."""
    signatures = _documented_keywords()
    for cell in notebook.cells:
        if cell.cell_type != "code" or "PLANNED SDK START" not in cell.text:
            continue
        tree = ast.parse(planned_code(cell=cell))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert | ast.Pass):
                message = f"Unnecessary assertion or placeholder in {cell.id}"
                raise TypeError(message)
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else (node.func.id if isinstance(node.func, ast.Name) else "")
            )
            if name not in signatures:
                continue
            supplied = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
            if not any(supplied <= allowed for allowed in signatures[name]):
                message = f"Undocumented keywords for {name} in {cell.id}: {supplied}"
                raise ValueError(message)


def _check_scene(*, scene: Scene) -> None:
    nodes = {node.id for node in scene.nodes}
    if len(nodes) != len(scene.nodes) or any(
        len(view.definitions) > MAX_VIEW_NODES for view in available_views(scene=scene)
    ):
        message = f"Invalid or unbounded model diagram in {scene.id}"
        raise ValueError(message)
    if any(edge.source not in nodes or edge.target not in nodes for edge in scene.edges):
        message = f"Dangling diagram reference in {scene.id}"
        raise ValueError(message)
    if any(len(row) != len(panel.columns) for panel in scene.panels for row in panel.rows):
        message = f"Nonrectangular table in {scene.id}"
        raise ValueError(message)


def _check_preview(*, entry: CoverageEntry, executable: Cell) -> None:
    if entry.preview_status == "replaced":
        if executable.id not in {step.cell_id for _, step in entry.contributions()}:
            message = f"Missing SDK evidence for the replaced preview in {entry.chapter}"
            raise ValueError(message)
    elif any(
        call not in executable.text for call in ("tour.display_snapshot", "tour.display_experiment")
    ):
        message = f"Missing executable preview or experiment in {entry.chapter}"
        raise ValueError(message)


def _check_entry(*, entry: CoverageEntry, scene: Scene, cells: dict[str, Cell]) -> None:
    if tuple(entry.owners) != scene.owners or tuple(entry.source_ids) != scene.sources:
        message = f"Coverage ownership/source drift in {entry.chapter}"
        raise ValueError(message)
    if entry.snapshot != scene.snapshot or not entry.expected_outcome:
        message = f"Missing expected outcome or wrong snapshot in {entry.chapter}"
        raise ValueError(message)
    for identity in entry.cell_ids:
        if identity not in cells or cells[identity].metadata.tour_id != identity:
            message = f"Missing or unstable cell: {identity}"
            raise ValueError(message)
    for test in entry.automated_checks:
        if not (ROOT / test).is_file():
            message = f"Missing referenced test: {test}"
            raise ValueError(message)
    _check_preview(entry=entry, executable=cells[f"{entry.chapter.lower()}-preview"])
    _check_scene(scene=scene)
    if set(entry.expected_definitions) != {item.name for item in scene.definitions}:
        msg = f"Coverage definition drift in {entry.chapter}"
        raise ValueError(msg)
    known_passages = {passage.id for source in scene.source_records for passage in source.passages}
    if not set(entry.source_passages) <= known_passages:
        msg = f"Unknown coverage passage in {entry.chapter}"
        raise ValueError(msg)


def _check_sdk_contributions(
    *, coverage: Coverage, cells: dict[str, Cell], source_pins: dict[str, str | None]
) -> None:
    covered_cells: set[str] = set()
    for entry in coverage.chapters:
        if (entry.sdk_status == "partial") != bool(entry.sdk_contributions):
            message = f"SDK evidence does not match the status of {entry.chapter}"
            raise ValueError(message)
        for owner, contribution in entry.contributions():
            cell = cells.get(contribution.cell_id)
            if (
                owner not in entry.owners
                or contribution.cell_id not in entry.cell_ids
                or cell is None
                or cell.cell_type != "code"
                or not ast.parse(cell.text).body
            ):
                message = f"Missing executable SDK cell for {owner} in {entry.chapter}"
                raise ValueError(message)
            pin = contribution.source_pin
            if (
                not contribution.expected_stdout.strip()
                or not contribution.automated_checks
                or any(not (ROOT / test).is_file() for test in contribution.automated_checks)
                or (pin is not None and source_pins.get(pin.source_id) != pin.sha256)
            ):
                message = f"Missing SDK evidence for {owner} in {entry.chapter}"
                raise ValueError(message)
            covered_cells.add(cell.id)
    if covered_cells != {cell.id for cell in cells.values() if "sdk" in cell.metadata.tags}:
        raise ValueError("SDK evidence must cover every cell tagged sdk.")


def _check_sdk_outputs(*, coverage: Coverage, cells: dict[str, Cell]) -> None:
    for entry in coverage.chapters:
        for _, contribution in entry.contributions():
            expected = contribution.expected_stdout
            if not any(
                output.get("output_type") == "stream"
                and output.get("name") == "stdout"
                and (output.get("text") in (expected, expected.splitlines(keepends=True)))
                for output in cells[contribution.cell_id].outputs
            ):
                message = f"Missing expected SDK output in {contribution.cell_id}"
                raise ValueError(message)


def check_coverage(
    *, notebook: Notebook, coverage: Coverage, check_saved_outputs: bool = True
) -> None:
    """Fail on missing chapters, dangling fixture references or falsely completed SDK work."""
    scenes = {scene.id: scene for scene in load_scenes()}
    cells = {cell.id: cell for cell in notebook.cells}
    if len(cells) != len(notebook.cells):
        raise ValueError("Notebook cell IDs must be unique.")
    if {entry.chapter for entry in coverage.chapters} != set(scenes):
        raise ValueError("Coverage must include all 21 chapter/exercise fixtures.")
    owners: set[str] = set()
    for entry in coverage.chapters:
        owners.update(entry.owners)
        _check_entry(entry=entry, scene=scenes[entry.chapter], cells=cells)
    if owners != {f"DK-{number:03}" for number in range(1, 44)}:
        raise ValueError("Each of the 43 roadmap owners needs a preview location.")
    for name, expected in coverage.fixture_hashes.items():
        path = FOLDER / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            message = f"Fixture pin changed: {name}; review and update the preview ledger."
            raise ValueError(message)
    check_planned_calls(notebook=notebook)
    catalogue = load_catalogue()
    sources = load_sources()
    check_catalogue(catalogue=catalogue, sources=sources)
    _check_sdk_contributions(
        coverage=coverage, cells=cells, source_pins={source.id: source.sha256 for source in sources}
    )
    if check_saved_outputs:
        _check_sdk_outputs(coverage=coverage, cells=cells)
    check_experiment_examples(scenes=tuple(scenes.values()), catalogue=catalogue)
    check_projection_examples(catalogue=catalogue, path=FOLDER / "fixtures/projections.json")
    check_discovery_lesson(lesson=load_discovery_lesson())
    learning = load_learning()
    check_learning(learning=learning)
    for method, keyword, identities in (
        ("display_practice", "exercise_id", {e.id for e in learning.practices}),
        (
            "display_discovery_example",
            "example_id",
            {e.id for e in load_discovery_lesson().examples},
        ),
        ("display_lesson_stage", "stage_id", {s.id for s in learning.stages}),
    ):
        referenced = {
            arg.value.value
            for cell in notebook.cells
            if cell.cell_type == "code"
            for node in ast.walk(ast.parse(cell.text))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method
            for arg in node.keywords
            if arg.arg == keyword
            and isinstance(arg.value, ast.Constant)
            and isinstance(arg.value.value, str)
        }
        if referenced != identities:
            message = f"Learning fixture/cell coverage differs for {method}"
            raise ValueError(message)


def check_pairing(*, notebook: Notebook) -> None:
    """Check both sources without synchronizing or rewriting them during validation."""
    import jupytext  # noqa: PLC0415 -- optional authoring dependency, never needed by core tests

    paired = Notebook.model_validate(jupytext.read(FOLDER / "domain-kernel-tour.py"))
    original = [(cell.metadata, cell.cell_type, cell.text) for cell in notebook.cells]
    text = [(cell.metadata, cell.cell_type, cell.text) for cell in paired.cells]
    if original != text:
        raise ValueError("Notebook/text sources differ; synchronize the intentional edit first.")


def execute(
    *,
    coverage: Coverage,
    write_outputs: bool = False,
    verify_resume: bool = False,
) -> None:
    """Execute offline in a fresh kernel; save reading artifacts only on explicit request."""
    import nbformat  # noqa: PLC0415 -- optional execution dependency
    from nbclient import NotebookClient  # noqa: PLC0415 -- optional execution dependency
    from nbconvert import HTMLExporter  # noqa: PLC0415 -- optional reading-build dependency

    document = nbformat.read(FOLDER / "domain-kernel-tour.ipynb", as_version=4)
    # Block internet connections in the kernel while retaining its local comms.
    guard = nbformat.v4.new_code_cell(
        "import socket\n"
        "_tour_socket_connect = socket.socket.connect\n"
        "def _tour_offline_connect(self, address):\n"
        "    if isinstance(address, tuple) and address[0] not in "
        "('127.0.0.1', '::1', 'localhost'):\n"
        "        raise RuntimeError('Network access is disabled during tour execution')\n"
        "    return _tour_socket_connect(self, address)\n"
        "socket.socket.connect = _tour_offline_connect\n"
    )
    document.cells.insert(0, guard)
    if verify_resume:
        document.cells.append(
            nbformat.v4.new_code_cell(
                "archived = await model.list_versions()\n"
                "assert archived.items[:2] == (bundle_v1, bundle_v2)\n"
                "pins = tuple(v.content_hash.value for v in archived.items)\n"
                "selected_branch = await pattern_model.get_version(version='1.0.0')\n"
                "assert selected_branch == branch_bundle\n"
                "dependency_archive = await dependency_model.get_version(version='1.0.0')\n"
                "assert dependency_archive == dependency_bundle\n"
                "print(model.scope.model_id.value, selected_branch.content_hash.value, "
                "dependency_archive.content_hash.value, *pins)\n"
            )
        )
    with TemporaryDirectory(prefix="domain-kernel-tour-") as workspace:
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        client = NotebookClient(document, timeout=90, kernel_name="python3")
        client.execute(cwd=workspace, env=env)
        if verify_resume:
            resumed = nbformat.from_dict(document)
            NotebookClient(resumed, timeout=90, kernel_name="python3").execute(
                cwd=workspace,
                env=env,
            )
            if resumed.cells[-1].outputs != document.cells[-1].outputs:
                raise ValueError("Resumed workspace changed the exact model or archived releases")
            document.cells.pop()
    document.cells.pop(0)
    observed = Notebook.model_validate(document)
    for cell in observed.cells:
        if cell.cell_type == "code" and not cell.outputs:
            message = f"No visible output from {cell.id}"
            raise ValueError(message)
        if any(output.get("output_type") == "error" for output in cell.outputs):
            message = f"Unexpected execution error in {cell.id}"
            raise ValueError(message)
    _check_sdk_outputs(coverage=coverage, cells={cell.id: cell for cell in observed.cells})
    if write_outputs:
        # Python-backed callbacks cannot work in an HTML file. Export the real static
        # outputs and explanations, without stale widget state or CDN-loaded scripts.
        # The saved notebook also keeps only static outputs: Run All creates fresh
        # widget comm IDs instead of asking frontends to revive a dead kernel's IDs.
        reading = nbformat.from_dict(document)
        reading.metadata.pop("widgets", None)
        for cell in reading.cells:
            if cell.cell_type == "code":
                cell.outputs = [
                    output
                    for output in cell.outputs
                    if "application/vnd.jupyter.widget-view+json" not in output.get("data", {})
                ]
        nbformat.write(reading, FOLDER / "domain-kernel-tour.ipynb")
        exporter = HTMLExporter(template_name="basic")
        html, _resources = exporter.from_notebook_node(reading)
        html = (
            (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>Domain Kernel Tour</title>"
                "<style>body{max-width:1180px;margin:40px auto;padding:0 24px;"
                "font:16px/1.65 system-ui,sans-serif}pre{white-space:pre-wrap}"
                "img,svg{max-width:100%}a{color:#087e8b}</style></head><body>"
            )
            + html
            + "</body></html>\n"
        )
        (FOLDER / "domain-kernel-tour.html").write_text(html)


def main() -> None:
    """Run read-only checks by default; artifact writing is an explicit build action."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run the complete offline tour")
    parser.add_argument(
        "--write-outputs", action="store_true", help="Execute and save reading outputs"
    )
    parser.add_argument(
        "--verify-resume",
        action="store_true",
        help="Rerun in a fresh kernel and verify the persisted releases",
    )
    args = parser.parse_args()
    notebook = Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())
    coverage = Coverage.model_validate_json((FOLDER / "coverage.json").read_bytes())
    check_coverage(notebook=notebook, coverage=coverage, check_saved_outputs=not args.write_outputs)
    check_pairing(notebook=notebook)
    if args.execute or args.write_outputs or args.verify_resume:
        execute(
            coverage=coverage,
            write_outputs=bool(args.write_outputs),
            verify_resume=bool(args.verify_resume),
        )
    sys.stdout.write(
        "Tour checks passed: 21 sections, 43 owners, pairing, fixture pins and SDK evidence.\n"
    )


if __name__ == "__main__":
    main()
