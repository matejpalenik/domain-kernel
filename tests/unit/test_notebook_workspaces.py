from pathlib import Path

import pytest

from examples.notebooks._preview.workspaces import select_demo_workspace


def test_fresh_selection_preserves_other_workspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    first = select_demo_workspace(name="recruitment")
    first.mkdir(parents=True)
    existing = first / "workspace.sqlite3"
    _ = existing.write_bytes(b"existing state")

    assert select_demo_workspace(name="recruitment") == first
    fresh = select_demo_workspace(name="recruitment-fresh")
    assert not fresh.exists()
    assert existing.read_bytes() == b"existing state"


def test_demo_selection_rejects_escape_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "business-data"
    outside.mkdir()
    Path("local").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="stay inside"):
        _ = select_demo_workspace(name="recruitment")
    with pytest.raises(ValueError, match="workspace name"):
        _ = select_demo_workspace(name="../../business-data")

    assert not list(outside.iterdir())
