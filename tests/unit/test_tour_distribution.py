"""Verify the contents and reproducibility of the separately shipped developer tour."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest

from development.tour_distribution import build_tour_archive, unpack_tour_archive

if TYPE_CHECKING:
    from pathlib import Path


_EXAMPLE_FILES = {
    "ARCHITECTURE.md": b"# Architecture\n",
    "INTERFACES.md": b"# Interfaces\n",
    "LICENSE": b"Apache-2.0\n",
    "README.md": b"# Domain Kernel\n",
    "ROADMAP.md": b"# Roadmap\n",
    "pyproject.toml": b'[project]\nname = "domain-kernel"\nversion = "1.0.0"\n',
    "uv.lock": b"version = 1\n",
    "examples/notebooks/README.md": b"# Tour\n",
    "examples/notebooks/domain-kernel-tour.html": b"<p>Tested output</p>\n",
    "examples/notebooks/domain-kernel-tour.ipynb": b"{}\n",
    "examples/notebooks/domain-kernel-tour.py": b"# Paired source\n",
    "examples/notebooks/fixtures/sources.json": b"[]\n",
    "examples/notebooks/coverage.json": json.dumps(
        {
            "schema_version": 1,
            "fixture_hashes": {},
            "chapters": [
                {
                    "chapter": "E10",
                    "notebook": "domain-kernel-tour.ipynb",
                    "cell_ids": [],
                    "owners": ["DK-042"],
                    "snapshot": "published",
                    "source_ids": [],
                    "preview_status": "implemented",
                    "sdk_status": "planned",
                    "expected_outcome": "Verify the SDK",
                    "human_acceptance": "Inspect a release",
                    "automated_checks": ["tests/unit/test_contract.py"],
                }
            ],
        },
    ).encode(),
    "tests/unit/test_contract.py": b"def test_contract(): pass\n",
}
_EXCLUDED = {
    ".env": b"OPENAI_API_KEY=fixture",
    "local/workspace/state.sqlite3": b"runtime state",
    "examples/notebooks/fixtures/original.pdf": b"publisher bytes",
    "examples/notebooks/.ipynb_checkpoints/tour.ipynb": b"stale notebook",
    "examples/notebooks/fixtures/.env": b"local credential",
    "src/domain_kernel/__init__.py": b"SDK package contents",
    "tests/unit/test_unrelated.py": b"unlinked evidence",
}


def _write_files(*, root: Path, files: dict[str, bytes]) -> None:
    for path, contents in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(contents)


def test_release_tour_contains_only_portable_assets(tmp_path: Path) -> None:
    files = _EXAMPLE_FILES | _EXCLUDED
    _write_files(root=tmp_path, files=files)
    first = build_tour_archive(
        root=tmp_path, tracked=tuple(files), output_directory=tmp_path / "first"
    )
    second = build_tour_archive(
        root=tmp_path, tracked=tuple(reversed(files)), output_directory=tmp_path / "second"
    )
    assert first.name == "domain-kernel-tour-1.0.0.zip"
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(file=first) as archive:
        assert set(archive.namelist()) == {*_EXAMPLE_FILES, "tour-manifest.json"}
        expected = {
            "sdk_version": "1.0.0",
            "files": {
                name: hashlib.sha256(data).hexdigest() for name, data in _EXAMPLE_FILES.items()
            },
        }
        assert (
            archive.read("tour-manifest.json")
            == (json.dumps(expected, indent=2, sort_keys=True) + "\n").encode()
        )
    extracted = tmp_path / "unpacked"
    unpack_tour_archive(source=first, destination=extracted)
    source_name = "examples/notebooks/domain-kernel-tour.py"
    assert (extracted / source_name).read_bytes() == _EXAMPLE_FILES[source_name]


def test_release_tour_requires_linked_acceptance_evidence(tmp_path: Path) -> None:
    files = dict(_EXAMPLE_FILES)
    del files["tests/unit/test_contract.py"]
    _write_files(root=tmp_path, files=files)
    with pytest.raises(ValueError, match=r"tests/unit/test_contract\.py"):
        _ = build_tour_archive(root=tmp_path, tracked=tuple(files), output_directory=tmp_path)
    assert not tuple(tmp_path.glob("*.zip"))


def test_release_tour_rejects_changed_packaged_bytes(tmp_path: Path) -> None:
    _write_files(root=tmp_path, files=_EXAMPLE_FILES)
    good = build_tour_archive(
        root=tmp_path, tracked=tuple(_EXAMPLE_FILES), output_directory=tmp_path
    )
    changed = tmp_path / "changed.zip"
    with ZipFile(file=good) as original, ZipFile(file=changed, mode="w") as copy:
        for name in original.namelist():
            data = (
                b"Different notebook output" if name.endswith("tour.html") else original.read(name)
            )
            copy.writestr(name, data)
    destination = tmp_path / "unpacked"
    with pytest.raises(ValueError, match=r"digest did not match"):
        unpack_tour_archive(source=changed, destination=destination)
    assert not destination.exists()
