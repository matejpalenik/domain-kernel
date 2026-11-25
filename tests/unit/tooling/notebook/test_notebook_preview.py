from __future__ import annotations

import pytest

from examples.notebooks._preview.validation import (
    FOLDER,
    Coverage,
    Notebook,
    check_coverage,
    restart_signature,
)


@pytest.fixture
def notebook() -> Notebook:
    return Notebook.model_validate_json((FOLDER / "domain-kernel-tour.ipynb").read_bytes())


@pytest.fixture
def coverage() -> Coverage:
    return Coverage.model_validate_json((FOLDER / "coverage.json").read_bytes())


def test_kernel_restart_signature_preserves_bytes_across_stream_frames() -> None:
    combined = [{"output_type": "stream", "name": "stdout", "text": "model sha256:bundle\n"}]
    split = [
        {"output_type": "stream", "name": "stdout", "text": "model "},
        {"output_type": "stream", "name": "stderr", "text": "Kernel diagnostic"},
        {"output_type": "stream", "name": "stdout", "text": ["sha256:", "bundle\n"]},
    ]
    assert restart_signature(outputs=combined) == restart_signature(outputs=split)
    split[-1]["text"] = "sha256:changed\n"
    assert restart_signature(outputs=combined) != restart_signature(outputs=split)


def test_walkthrough_discloses_and_uses_live_pdf_and_inference(notebook: Notebook) -> None:
    assert "OPENAI_API_KEY" in notebook.cells[0].text
    code = "\n".join(cell.text for cell in notebook.cells if cell.cell_type == "code")
    assert "DoclingParser()" in code
    assert "LiteLLMGateway(" in code
    assert "Retention(extracted_text=True)" in code
    assert "ParsedSource(" not in code
    assert "ReplayGateway" not in code


def test_notebook_outputs_start_with_evidence_and_show_the_release(notebook: Notebook) -> None:
    first_code = next(cell for cell in notebook.cells if cell.cell_type == "code")
    assert "Verified PDF:" in restart_signature(outputs=first_code.outputs)
    evidence = next(cell for cell in notebook.cells if cell.id == "c3-sdk-docling")
    assert "Saved text from 144 PDF pages in SQLite" in restart_signature(outputs=evidence.outputs)
    release = next(cell for cell in notebook.cells if cell.id == "c9-sdk-portable")
    assert "Complete published model · 1.0.0 · 5 definitions" in restart_signature(
        outputs=release.outputs
    )


def test_coverage_rejects_missing_cells_and_changed_fixture_pins(
    notebook: Notebook, coverage: Coverage
) -> None:
    incomplete = notebook.model_copy(
        update={"cells": [cell for cell in notebook.cells if cell.id != "c9-sdk-portable"]}
    )
    with pytest.raises(ValueError, match="Missing executable SDK cell"):
        check_coverage(notebook=incomplete, coverage=coverage)
    changed = coverage.model_copy(update={"fixture_hashes": {"fixtures/sources.json": "invalid"}})
    with pytest.raises(ValueError, match="Fixture pin changed"):
        check_coverage(notebook=notebook, coverage=changed)


def test_coverage_rejects_a_missing_owner_or_test(notebook: Notebook, coverage: Coverage) -> None:
    coverage.supporting[-1].owners = ["DK-044"]
    with pytest.raises(ValueError, match="43 v1 capability IDs"):
        check_coverage(notebook=notebook, coverage=coverage)
    coverage.supporting[-1].owners = ["DK-041", "DK-042", "DK-043"]
    coverage.steps[0].automated_checks = ["tests/missing.py"]
    with pytest.raises(ValueError, match="Missing or invalid acceptance evidence"):
        check_coverage(notebook=notebook, coverage=coverage)


@pytest.mark.parametrize(
    ("update", "error"),
    [
        ({"source": "# Future SDK operation"}, "Missing executable SDK cell"),
        ({"source": "pass\n..."}, "Missing executable SDK cell"),
        ({"outputs": []}, "Missing expected SDK output"),
    ],
)
def test_sdk_coverage_requires_executable_cells_and_observed_output(
    notebook: Notebook, coverage: Coverage, update: dict[str, object], error: str
) -> None:
    notebook.cells = [
        cell.model_copy(update=update) if cell.id == "c9-sdk-portable" else cell
        for cell in notebook.cells
    ]
    with pytest.raises(ValueError, match=error):
        check_coverage(notebook=notebook, coverage=coverage)
