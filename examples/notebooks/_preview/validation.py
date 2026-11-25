"""Check the evidence-first walkthrough and build its offline reading version."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from domain_kernel.shared.validation import is_non_string_sequence
from examples.notebooks._preview.catalogue import load_sources

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from nbformat import NotebookNode

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT / "examples" / "notebooks"
STEPS = ("evidence", "draft", "review", "publish")


class CellMetadata(BaseModel):
    """Metadata shared by the notebook and its text representation."""

    tour_id: str
    tags: list[str] = Field(default_factory=list)


class Cell(BaseModel):
    """Typed read boundary for notebook cells."""

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
    """The cells are the common contract between the paired files."""

    cells: list[Cell]


class EvidenceLocation(BaseModel):
    """Associate v1 capability IDs with repeatable verification."""

    owners: list[str] = Field(min_length=1)
    automated_checks: list[str] = Field(min_length=1)


class WalkthroughStep(EvidenceLocation):
    """Record the visible result and exact sources for one step."""

    anchor: str
    expected_output: dict[str, list[str]] = Field(min_length=1)
    sources: dict[str, str] = Field(min_length=1)


class SupportingEvidence(EvidenceLocation):
    """Locate specialized examples and conformance outside the walkthrough."""

    capability: str
    recipes: list[str] = Field(default_factory=list)


class Coverage(BaseModel):
    """Ledger for the runnable journey and all supporting ticket evidence."""

    schema_version: Literal[2]
    fixture_hashes: dict[str, str]
    steps: list[WalkthroughStep]
    supporting: list[SupportingEvidence]

    def checks(self) -> set[str]:
        """Return the test paths backing the walkthrough and supporting capabilities."""
        return {
            path for entry in [*self.steps, *self.supporting] for path in entry.automated_checks
        }


def restart_signature(*, outputs: Sequence[Mapping[str, object]]) -> str:
    """Read stdout across kernel stream frames."""
    parts: list[str] = []
    for output in outputs:
        if output.get("output_type") != "stream" or output.get("name") != "stdout":
            continue
        value = output.get("text")
        if isinstance(value, str):
            parts.append(value)
        elif is_non_string_sequence(value) and all(isinstance(line, str) for line in value):
            parts.extend(line for line in value if isinstance(line, str))
        else:
            raise ValueError("Kernel stdout must contain text.")
    return "".join(parts)


def _existing_path(*, name: str, folder: Path) -> Path:
    path = folder / name
    if not path.resolve().is_relative_to(folder) or not path.is_file():
        msg = f"Missing or invalid acceptance evidence: {name}"
        raise ValueError(msg)
    return path


def _check_steps(*, coverage: Coverage, notebook: Notebook, saved: bool) -> None:
    ids = [cell.id for cell in notebook.cells]
    if len(set(ids)) != len(ids) or any(
        cell.id != cell.metadata.tour_id for cell in notebook.cells
    ):
        raise ValueError("Notebook cell IDs must be unique and match tour_id.")
    anchors = [
        anchor
        for cell in notebook.cells
        if cell.cell_type == "markdown"
        for anchor in STEPS
        if f'<a id="{anchor}"></a>' in cell.text
    ]
    if anchors != list(STEPS) or tuple(step.anchor for step in coverage.steps) != STEPS:
        raise ValueError("Notebook and ledger must follow the evidence-to-publication journey.")
    executable = {cell.id: cell for cell in notebook.cells if cell.cell_type == "code"}
    expected = {cell_id for step in coverage.steps for cell_id in step.expected_output}
    if executable.keys() != expected:
        raise ValueError("Missing executable SDK cell or acceptance output in the ledger.")
    pins = {source.id: source.sha256 for source in load_sources()}
    for step in coverage.steps:
        for name, digest in step.sources.items():
            if not digest or digest != pins.get(name):
                msg = f"Source pin changed: {name}"
                raise ValueError(msg)
        for cell_id, fragments in step.expected_output.items():
            _check_cell(cell=executable[cell_id], fragments=fragments, saved=saved)


def _check_cell(*, cell: Cell, fragments: Sequence[str], saved: bool) -> None:
    if not any(
        not isinstance(node, ast.Pass)
        and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        for node in ast.parse(cell.text).body
    ):
        msg = f"Missing executable SDK cell: {cell.id}"
        raise ValueError(msg)
    output = " ".join(restart_signature(outputs=cell.outputs).split())
    if not fragments or any(
        not fragment.strip() or (saved and fragment not in output) for fragment in fragments
    ):
        msg = f"Missing expected SDK output in {cell.id}"
        raise ValueError(msg)
    if any(item.get("output_type") == "error" for item in cell.outputs):
        msg = f"Unexpected execution error in {cell.id}"
        raise ValueError(msg)


def check_coverage(
    *, notebook: Notebook, coverage: Coverage, check_saved_outputs: bool = True
) -> None:
    """Require repeatable acceptance evidence for each of the 43 v1 capability IDs."""
    owners = {owner for entry in [*coverage.steps, *coverage.supporting] for owner in entry.owners}
    if owners != {f"DK-{number:03}" for number in range(1, 44)}:
        raise ValueError("Each of the 43 v1 capability IDs needs acceptance evidence.")
    for name in coverage.checks():
        _ = _existing_path(name=name, folder=ROOT)
    for entry in coverage.supporting:
        for recipe in entry.recipes:
            _ = _existing_path(name=recipe, folder=ROOT)
    for name, expected in coverage.fixture_hashes.items():
        path = _existing_path(name=name, folder=FOLDER)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            msg = f"Fixture pin changed: {name}; review and update the ledger."
            raise ValueError(msg)
    _check_steps(coverage=coverage, notebook=notebook, saved=check_saved_outputs)


def check_pairing(*, notebook: Notebook) -> None:
    """Check pairing without rewriting either file."""
    import jupytext  # noqa: PLC0415 -- optional authoring dependency

    paired = Notebook.model_validate(jupytext.read(FOLDER / "domain-kernel-tour.py"))
    original = [(cell.metadata, cell.cell_type, cell.text) for cell in notebook.cells]
    text = [(cell.metadata, cell.cell_type, cell.text) for cell in paired.cells]
    if original != text:
        raise ValueError("Notebook/text sources differ. Synchronize the intentional edit first.")


_OFFLINE_GUARD = """
import sys

def _walkthrough_offline(event, args):
    loopback = ("127.0.0.1", "::1", "localhost")
    if event == "socket.getaddrinfo" and args[0] not in loopback:
        raise RuntimeError("External DNS is disabled during restart verification.")
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address[0] not in loopback:
            raise RuntimeError("External connections are disabled during restart verification.")

sys.addaudithook(_walkthrough_offline)
"""


def _kernel_start(*, bootstrap: str, offline: bool) -> str:
    guard = _OFFLINE_GUARD if offline else ""
    if (prefix := os.environ.get("DK_TOUR_INSTALLED_SDK_PREFIX")) is not None:
        guard += (
            "from pathlib import Path\n"
            "import sys\n"
            "import domain_kernel\n"
            f"_installed_sdk_prefix = Path({prefix!r}).resolve()\n"
            "assert Path(sys.prefix).resolve() == _installed_sdk_prefix\n"
            "assert Path(domain_kernel.__file__).resolve().is_relative_to(_installed_sdk_prefix)\n"
        )
    return guard + "\n" + bootstrap


_RESTART_CHECK = r"""
from domain_kernel import AuditAction

assert tuple(item.name for item in (await project.list_models()).items) == ("ai-in-recruitment",)
assert (await model.list_versions()).items == (bundle,)
assert bundle_file.read_bytes() == release.serialize()
assert (await model.list_discovery_runs()).items == (run,)
assert not (await model.list_review_cases(status=CaseStatus.PENDING)).items
assert set(pages) == set(range(1, 145))
assert (await retained_project.get_evidence(evidence=pages[59])) == article_13
assert budget.usage().attempts > 0

decisions = []
async for case in model.iter_review_cases():
    (receipt,) = (await model.get_review_history(case_id=case.id)).items
    assert receipt.actor == reviewer
    decisions.append(receipt.id.value)
publications = [
    event for event in (await model.get_audit_history(limit=100)).items
    if event.action is AuditAction.PUBLISH
]
assert len(publications) == 1 and publications[0].actor == publisher
print(budget.usage())
print(model.scope.model_id.value, run.id.value, *sorted(decisions),
      bundle_file, delivery.content_hash.value, pdf.digest.value, sep="\n")
"""

_CONSUMER_CHECK = """
import sys
from pathlib import Path

from domain_kernel import (
    ContentHash, DocumentSpan, DomainModelBundle, FileOrigin,
    RelationshipDefinition, RuleDefinition,
)

def files_only(event, _args):
    if event.startswith("socket.") or event == "sqlite3.connect":
        raise RuntimeError("The consumer only reads the delivered files.")

sys.addaudithook(files_only)
path, digest, act_digest = sys.argv[1:]
bundle = DomainModelBundle.deserialize(
    payload=Path(path).read_bytes(), expected_hash=ContentHash(value=digest),
)
assert bundle.version == "1.0.0"
instructions = bundle.get_concept(name="instructions-for-use")
technical = bundle.get_concept(name="technical-documentation")
provider = bundle.get_concept(name="provider")
assert len({instructions.id, technical.id, provider.id}) == 3
assert "help the deployer use the system" in instructions.meaning
assert "support assessment" in technical.meaning
assert not instructions.get_attribute(name="logging-mechanisms").required
definitions = {item.name: item for item in bundle.content.definitions}
rule = definitions["logging-qualification"]
assert isinstance(rule.body, RuleDefinition) and rule.body.statement.startswith("Where relevant")
supplies = definitions["supplies-instructions"]
assert isinstance(supplies.body, RelationshipDefinition)
assert supplies.body.source_concept_id == provider.id
assert supplies.body.target_concept_id == instructions.id

expected_pages = {
    "provider": {46},
    "instructions-for-use": {59, 60},
    "technical-documentation": {58},
    "logging-qualification": {60},
    "supplies-instructions": {59, 62},
}
assert definitions.keys() == expected_pages.keys()
for name, definition in definitions.items():
    assert definition.evidence
    for citation in definition.evidence:
        assert isinstance(citation.locator, DocumentSpan)
        assert citation.locator.page in expected_pages[name]
        assert isinstance(citation.source.origin, FileOrigin)
        assert citation.source.revision_id.value == act_digest
"""


def _write_reading(*, document: NotebookNode) -> None:
    import nbformat  # noqa: PLC0415 -- optional execution dependency
    from nbconvert import HTMLExporter  # noqa: PLC0415 -- optional reading-build dependency

    nbformat.write(document, FOLDER / "domain-kernel-tour.ipynb")
    html, _ = HTMLExporter(template_name="basic").from_notebook_node(document)
    (FOLDER / "domain-kernel-tour.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>From AI Act evidence to a model you can ship</title>"
        "<style>:root{color-scheme:light dark}body{max-width:860px;margin:2rem auto;"
        "padding:0 1rem;font:16px/1.6 system-ui,sans-serif;overflow-wrap:anywhere}"
        "pre{white-space:pre-wrap;font-size:.875rem;overflow-wrap:anywhere}"
        ".input_area,.output_area{padding:.25rem .75rem;background:light-dark(#f1f5f9,#1e293b)}"
        "a{color:light-dark(#145597,#93c5fd)}</style></head><body><main>"
        + html
        + "</main></body></html>\n"
    )


def execute(
    *,
    coverage: Coverage,
    write_outputs: bool = False,
    verify_resume: bool = False,
    bootstrap: str = "",
) -> None:
    """Run the live workspace or test isolation and check offline restart."""
    import nbformat  # noqa: PLC0415 -- optional execution dependency
    from nbclient import NotebookClient  # noqa: PLC0415 -- optional execution dependency

    if bootstrap and write_outputs:
        raise ValueError("Save reading outputs from a live run.")
    document = nbformat.read(FOLDER / "domain-kernel-tour.ipynb", as_version=4)
    guard = _kernel_start(bootstrap=bootstrap, offline=bool(bootstrap))
    document.cells.insert(0, nbformat.v4.new_code_cell(guard))
    if verify_resume:
        document.cells.append(nbformat.v4.new_code_cell(_RESTART_CHECK))
    isolated = (
        TemporaryDirectory(prefix="domain-kernel-tour-") if bootstrap else nullcontext(str(ROOT))
    )
    with isolated as workspace:
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        NotebookClient(document, timeout=180, kernel_name="python3").execute(cwd=workspace, env=env)
        if verify_resume:
            resumed = nbformat.from_dict(document)
            resumed.cells[0].source = _kernel_start(bootstrap=bootstrap, offline=True)
            NotebookClient(resumed, timeout=180, kernel_name="python3").execute(
                cwd=workspace, env=env
            )
            initial = restart_signature(outputs=document.cells[-1].outputs)
            replay = restart_signature(outputs=resumed.cells[-1].outputs)
            if not initial or replay != initial:
                raise ValueError("Restart changed the release, review decisions or provider usage.")
            _ = subprocess.run(  # noqa: S603 -- fixed file-only consumer
                [sys.executable, "-I", "-c", _CONSUMER_CHECK, *initial.splitlines()[-3:]],
                cwd=workspace,
                timeout=30,
                check=True,
            )
            document.cells.pop()
            sys.stdout.write(
                "Verified the full model after restart with zero new provider attempts.\n"
            )
    document.cells.pop(0)
    _check_steps(coverage=coverage, notebook=Notebook.model_validate(document), saved=True)
    if write_outputs:
        for cell in document.cells:
            cell.metadata.pop("execution", None)
        _write_reading(document=document)


def main() -> None:
    """Check saved evidence by default, with execution and writing opt-in."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Run the live PDF and Luna walkthrough"
    )
    parser.add_argument("--write-outputs", action="store_true", help="Execute and save the outputs")
    parser.add_argument(
        "--verify-resume",
        action="store_true",
        help="Verify the published model on an offline restart",
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
    sys.stdout.write("Walkthrough checks passed: pairing, source pins, outputs and 43 owners.\n")


if __name__ == "__main__":
    main()
