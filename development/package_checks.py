"""Verify exact built SDK distributions and the portable guide in isolated environments."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from development.tour_distribution import unpack_tour_archive
from examples.notebooks.originals import MANUFACTURING_ENV

if TYPE_CHECKING:
    from collections.abc import Sequence

_ROOT = Path(__file__).resolve().parents[1]
_CHECKS = {
    "documents": ("docling", "tests/integration/test_docling_sources.py"),
    "inference": ("litellm", "tests/unit/test_litellm_gateway.py"),
    "linkml": ("linkml_runtime", "tests/integration/test_linkml_projection.py"),
    "matching": ("rapidfuzz", "tests/integration/test_reconciliation.py"),
    "ontology": ("rdflib", "tests/integration/test_ontology_loading.py"),
    "postgres": ("psycopg", "tests/integration/test_postgresql.py"),
    "s3": (
        "boto3",
        "tests/integration/test_remote_adapters.py::test_s3_pages_and_reads_the_inspected_version",
        "tests/integration/test_remote_adapters.py::test_s3_artifact_recovers_only_the_exact_conditional_write",
    ),
    "sharepoint": (
        "httpx",
        "tests/integration/test_remote_adapters.py::test_graph_download_keeps_credentials_at_graph",
        "tests/integration/test_remote_adapters.py::test_graph_cancellation_releases_the_request_without_closing_borrowed_client",
        "tests/integration/test_remote_adapters.py::test_entra_authentication_uses_the_tenant_and_sanitizes_provider_failures",
    ),
    "tabular": ("duckdb", "tests/integration/test_tabular_sources.py"),
}
_NOTEBOOK_EXTRAS = ("ontology", "linkml", "tabular", "s3", "sharepoint", "postgres")
_SMOKE = """
import sys
from importlib.metadata import metadata
from importlib.resources import files
from importlib.util import find_spec
from pathlib import Path
import domain_kernel

package = files("domain_kernel")
assert Path(domain_kernel.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert package.joinpath("py.typed").is_file()
assert metadata("domain-kernel")["License-Expression"] == "Apache-2.0"
assert metadata("domain-kernel")["Requires-Python"] == ">=3.13"
mode, *modules = sys.argv[1:]
for module in modules:
    assert module not in sys.modules, module
    assert (find_spec(module) is not None) == (mode == "installed"), module
"""
_TYPED_CONSUMER = """
from domain_kernel import Concept, DomainModelBundle, validate_bundle

def inspect(*, contents: bytes, name: str) -> Concept:
    bundle = DomainModelBundle.deserialize(payload=contents)
    assert validate_bundle(bundle=bundle).valid
    return bundle.get_concept(name=name)
"""


def _run(*, args: Sequence[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    _ = subprocess.run(args, cwd=cwd, env=env, check=True)  # noqa: S603 -- fixed local commands


def _tool(*, name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        message = f"Install {name} before checking the packaged SDK."
        raise ValueError(message)
    return tool


def _install(  # noqa: PLR0913 -- independent setup inputs shared by the matrix and tour
    *,
    root: Path,
    environment: Path,
    artifact: Path,
    python: str,
    groups: Sequence[str] = (),
    extras: Sequence[str] = (),
) -> Path:
    uv = _tool(name="uv")
    sync = [
        uv,
        "sync",
        "--locked",
        "--no-install-project",
        "--no-default-groups",
        "--python",
        python,
    ]
    for group in groups:
        sync.extend(("--group", group))
    for extra in extras:
        sync.extend(("--extra", extra))
    _run(args=sync, cwd=root, env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(environment)})
    executable = environment / "bin/python"
    _run(
        args=[uv, "pip", "install", "--no-deps", "--python", str(executable), str(artifact)],
        cwd=root,
    )
    return executable


def _check_types(*, runtime: Path, folder: Path, python: str) -> None:
    _ = (folder / "consumer.py").write_text(_TYPED_CONSUMER, encoding="utf-8")
    config = {"include": ["consumer.py"], "typeCheckingMode": "all", "pythonVersion": python}
    _ = (folder / "pyrightconfig.json").write_text(json.dumps(config), encoding="utf-8")
    _run(
        args=[
            sys.executable,
            "-m",
            "basedpyright",
            "--project",
            str(folder),
            "--pythonpath",
            str(runtime),
        ],
        cwd=folder,
    )


def _verify_profile(*, folder: Path, artifact: Path, python: str, extras: tuple[str, ...]) -> None:
    runtime = _install(
        root=_ROOT,
        environment=folder / "environment",
        artifact=artifact,
        python=python,
        groups=("dev",) if extras else (),
        extras=extras,
    )
    modules = (
        [_CHECKS[extra][0] for extra in extras]
        if extras
        else [module for module, *_ in _CHECKS.values()]
    )
    _run(
        args=[str(runtime), "-I", "-c", _SMOKE, "installed" if extras else "absent", *modules],
        cwd=folder,
    )
    _check_types(runtime=runtime, folder=folder, python=python)
    if extras:
        suite = [test for extra in extras for test in _CHECKS[extra][1:]]
        _run(args=[str(runtime), "-m", "pytest", *suite], cwd=_ROOT)
    else:
        _run(args=[str(runtime), str(_ROOT / "examples/recruitment_quickstart.py")], cwd=folder)


class _Project(BaseModel):
    extras: dict[str, list[str]] = Field(alias="optional-dependencies")


def _verify_matrix(*, wheel: Path, source: Path, python: str) -> None:
    table: object = tomllib.loads((_ROOT / "pyproject.toml").read_text()).get("project")
    project = _Project.model_validate(table)
    if project.extras.keys() != _CHECKS.keys():
        raise ValueError("Add a matrix scenario for every declared runtime extra.")
    if "DK_TEST_POSTGRES_DSN" not in os.environ:
        raise ValueError("Provide a disposable PostgreSQL DSN for the install matrix.")
    profiles: dict[str, tuple[str, ...]] = {
        "core-wheel": (),
        "core-sdist": (),
        **{name: (name,) for name in _CHECKS},
    }
    profiles["combined"] = tuple(_CHECKS)
    for profile, extras in profiles.items():
        _ = sys.stdout.write(f"Checking {profile} on Python {python}\n")
        _ = sys.stdout.flush()
        with TemporaryDirectory(prefix=f"domain-kernel-{profile}-") as workspace:
            _verify_profile(
                folder=Path(workspace),
                artifact=source if profile == "core-sdist" else wheel,
                python=python,
                extras=extras,
            )


def _verify_tour(*, wheel: Path, tour: Path, python: str, resume: bool) -> None:
    with TemporaryDirectory(prefix="domain-kernel-packaged-tour-") as workspace:
        root = Path(workspace)
        unpack_tour_archive(source=tour, destination=root)
        extras = _NOTEBOOK_EXTRAS
        if "DOMAIN_KERNEL_TOUR_DOCLING_MODELS" in os.environ or MANUFACTURING_ENV in os.environ:
            extras = (*extras, "documents")
        runtime = _install(
            root=root,
            environment=root / ".venv",
            artifact=wheel,
            python=python,
            groups=("notebook",),
            extras=extras,
        )
        _run(args=[str(runtime), "-I", "-c", _SMOKE, "installed"], cwd=root)
        _run(args=[str(runtime), "-m", "examples.recruitment_quickstart"], cwd=root)
        if "DOMAIN_KERNEL_TOUR_POSTGRES_DSN" in os.environ:
            _run(args=[str(runtime), "-m", "examples.notebooks.postgres_tour"], cwd=root)
        if originals := os.environ.get(MANUFACTURING_ENV):
            delivery = root / "manufacturing-delivery"
            _run(
                args=[
                    str(runtime),
                    "-m",
                    "examples.manufacturing_quickstart",
                    "--originals",
                    originals,
                    "--output",
                    str(delivery),
                ],
                cwd=root,
            )
            _run(
                args=[
                    str(runtime),
                    "-m",
                    "examples.embedding_acceptance",
                    "--delivery",
                    str(delivery),
                ],
                cwd=root,
            )
        _run(
            args=[
                str(runtime),
                "-m",
                "examples.notebooks._preview.validation",
                "--verify-resume" if resume else "--execute",
            ],
            cwd=root,
            env={**os.environ, "DK_TOUR_INSTALLED_SDK_PREFIX": str(root / ".venv")},
        )


class _Options(argparse.Namespace):
    python: str = ""
    wheel: Path = Path()
    source: Path | None = None
    tour: Path | None = None
    resume: bool = False


def main() -> None:
    """Check the extra matrix or execute the guide from its portable archive."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--python", required=True, choices=("3.13", "3.14"))
    _ = parser.add_argument("--wheel", required=True, type=Path)
    check = parser.add_mutually_exclusive_group(required=True)
    _ = check.add_argument("--source", type=Path)
    _ = check.add_argument("--tour", type=Path)
    _ = parser.add_argument("--resume", action="store_true")
    options = parser.parse_args(namespace=_Options())
    if options.source is not None:
        _verify_matrix(
            wheel=options.wheel.resolve(), source=options.source.resolve(), python=options.python
        )
    elif options.tour is not None:
        _verify_tour(
            wheel=options.wheel.resolve(),
            tour=options.tour.resolve(),
            python=options.python,
            resume=options.resume,
        )


if __name__ == "__main__":
    main()
