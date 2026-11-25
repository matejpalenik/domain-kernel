from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from tests.support.repository_root import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.notebook]


@pytest.mark.parametrize("extra", [(), ("--invalid-endpoint",)], ids=["valid", "invalid-endpoint"])
def test_tour_executes_offline_and_preserves_model_after_kernel_restart(
    extra: tuple[str, ...],
) -> None:
    result = subprocess.run(  # noqa: S603 -- pytest selects the fixed local harness flags.
        [sys.executable, "tests/support/notebook/tour.py", "--verify-resume", *extra],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verified the full model after restart with zero new provider attempts." in result.stdout


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
        .replace(
            "# # From AI Act evidence to a model you can ship",
            "# # From AI Act evidence to a model you can ship — sync test",
            1,
        )
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
    assert after.cells[2].outputs == before.cells[2].outputs
