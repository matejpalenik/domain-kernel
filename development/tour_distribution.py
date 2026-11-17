"""Package the canonical tour and its evidence without including runtime state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pydantic import BaseModel

from examples.notebooks._preview.validation import Coverage

if TYPE_CHECKING:
    from collections.abc import Sequence

_ROOT = Path(__file__).resolve().parents[1]
_LEDGER = "examples/notebooks/coverage.json"
_REQUIRED = frozenset(
    {
        "ARCHITECTURE.md",
        "INTERFACES.md",
        "LICENSE",
        "README.md",
        "ROADMAP.md",
        "pyproject.toml",
        "uv.lock",
        _LEDGER,
        "examples/notebooks/README.md",
        "examples/notebooks/domain-kernel-tour.html",
        "examples/notebooks/domain-kernel-tour.ipynb",
        "examples/notebooks/domain-kernel-tour.py",
        "examples/notebooks/fixtures/sources.json",
    }
)
_GUIDES = frozenset({"CONTRIBUTING.md", "SECURITY.md"})
_NOTEBOOK_SUFFIXES = {".csv", ".html", ".ipynb", ".java", ".json", ".md", ".py"}
_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_READABLE_FILE = 0o100644 << 16


def _portable_path(*, name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or str(path) != name
        or ":" in name
        or "\\" in name
        or any(part.startswith(".") for part in path.parts)
    ):
        raise ValueError("Select a relative, visible file for the tour archive.")
    return path


def _recipe(*, path: PurePosixPath) -> bool:
    match path.parts:
        case ("examples", "notebooks", *_):
            return path.suffix in _NOTEBOOK_SUFFIXES
        case ("examples", "config", filename):
            return filename == "README.md" or (
                filename.startswith("domain-kernel.") and path.suffix == ".toml"
            )
        case ("examples", _):
            return path.suffix in {".md", ".py"}
        case ("docs", _):
            return path.suffix == ".md"
        case _:
            return False


def _evidence_paths(*, ledger: Coverage) -> set[str]:
    references = {
        test
        for chapter in ledger.chapters
        for test in (
            *chapter.automated_checks,
            *(path for _, step in chapter.contributions() for path in step.automated_checks),
        )
    }
    for name in references:
        path = _portable_path(name=name)
        python_test = path.parts[0] == "tests" and path.suffix == ".py"
        browser_test = path.parts[:3] == ("apps", "docs", "notebook-tests") and name.endswith(
            ".spec.ts"
        )
        if not (python_test or browser_test):
            raise ValueError("Reference a checked-in test for tour evidence.")
    return references


def _inputs(*, root: Path, tracked: Sequence[str]) -> dict[str, bytes]:
    ledger = Coverage.model_validate_json((root / _LEDGER).read_bytes())
    required = _REQUIRED | _evidence_paths(ledger=ledger)
    if missing := required.difference(tracked):
        message = f"Required tour files are missing: {', '.join(sorted(missing))}"
        raise ValueError(message)
    result: dict[str, bytes] = {}
    for name in sorted(set(tracked)):
        path = PurePosixPath(name)
        if any(part.startswith(".") for part in path.parts):
            continue
        if name not in required | _GUIDES and not _recipe(path=path):
            continue
        relative = _portable_path(name=name)
        file = root.joinpath(*relative.parts)
        if file.resolve() != file.absolute() or not file.is_file():
            message = f"Ship a regular file for {name}."
            raise ValueError(message)
        result[name] = file.read_bytes()
    return result


def _sdk_version(*, contents: bytes) -> str:
    project: object = tomllib.loads(contents.decode()).get("project")
    match project:
        case {"name": "domain-kernel", "version": str(version)} if re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+[a-z0-9.+-]*", version
        ):
            return version
        case _:
            raise ValueError("Set the Domain Kernel version in the packaged project metadata.")


def build_tour_archive(*, root: Path, tracked: Sequence[str], output_directory: Path) -> Path:
    """Create the versioned reproducible tour ZIP with exact evidence and asset hashes."""
    inputs = _inputs(root=root.resolve(), tracked=tracked)
    version = _sdk_version(contents=inputs["pyproject.toml"])
    manifest = (
        json.dumps(
            {
                "sdk_version": version,
                "files": {name: sha256(contents).hexdigest() for name, contents in inputs.items()},
            },
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / f"domain-kernel-tour-{version}.zip"
    with ZipFile(file=destination, mode="w") as archive:
        for name, payload in (*inputs.items(), ("tour-manifest.json", manifest)):
            item = ZipInfo(filename=name, date_time=_TIMESTAMP)
            item.create_system = 3
            item.external_attr = _READABLE_FILE
            archive.writestr(zinfo_or_arcname=item, data=payload, compress_type=ZIP_DEFLATED)
    return destination


class _TourManifest(BaseModel):
    sdk_version: str
    files: dict[str, str]


def unpack_tour_archive(*, source: Path, destination: Path) -> None:
    """Verify every named asset before unpacking the released tour for a smoke test."""
    with ZipFile(file=source) as archive:
        manifest = _TourManifest.model_validate_json(archive.read("tour-manifest.json"))
        entries = archive.namelist()
        if (
            set(entries) != {"tour-manifest.json", *manifest.files}
            or len(entries) != len(set(entries))
            or _REQUIRED.difference(manifest.files)
        ):
            raise ValueError("The tour files do not match the distribution manifest.")
        ledger = Coverage.model_validate_json(archive.read(_LEDGER))
        evidence = _evidence_paths(ledger=ledger)
        expected = _REQUIRED | _GUIDES | evidence
        if missing := evidence.difference(manifest.files):
            message = f"Required tour evidence is missing: {', '.join(sorted(missing))}"
            raise ValueError(message)
        payloads: dict[PurePosixPath, bytes] = {}
        for name, digest in manifest.files.items():
            path = _portable_path(name=name)
            if name not in expected and not _recipe(path=path):
                raise ValueError("The tour contains an unexpected file.")
            payload = archive.read(name)
            if sha256(payload).hexdigest() != digest:
                message = f"The packaged tour digest did not match for {name}."
                raise ValueError(message)
            payloads[path] = payload
    if manifest.sdk_version != _sdk_version(contents=payloads[PurePosixPath("pyproject.toml")]):
        raise ValueError("The tour version disagrees with its package metadata.")
    for path, payload in payloads.items():
        target = destination.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(payload)


def tracked_tour_files(*, root: Path) -> tuple[str, ...]:
    """Select checked-in inputs so local files are never eligible for publication."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached"],  # noqa: S607 -- use the development toolchain
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    )
    return tuple(name for name in result.stdout.split("\0") if name)


class _Options(argparse.Namespace):
    out_dir: Path = Path("dist")


def main() -> None:
    """Build the separate notebook distribution from the current checked-out inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--out-dir", type=Path, default=Path("dist"))
    options = parser.parse_args(namespace=_Options())
    destination = build_tour_archive(
        root=_ROOT, tracked=tracked_tour_files(root=_ROOT), output_directory=options.out_dir
    )
    _ = sys.stdout.write(f"{destination}\n")


if __name__ == "__main__":
    main()
