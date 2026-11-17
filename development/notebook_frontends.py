"""Expose a disposable notebook fixture to Playwright on a local Jupyter server."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

_ROOT = Path(__file__).resolve().parents[1]
_CELL = dedent(
    """
    from pathlib import Path
    from IPython.display import display
    from domain_kernel import Client, ClientConfiguration, enable_notebook_display
    from examples.recruitment_quickstart import author_releases
    from examples.notebooks.live_controls import demo_review, inspect_release, ReviewControls

    workspace = Path.cwd() / "fixture-workspace"
    _, release = await author_releases(workspace=workspace)
    project = await Client(config=ClientConfiguration(base_dir=workspace)).get_project(
        name="recruitment-legislation"
    )
    review_model, review_case = await demo_review(project=project)
    enable_notebook_display()
    display(release)
    display(inspect_release(release=release))
    display(ReviewControls(model=review_model, case=review_case, actor="browser-reviewer").widget)
    print(f"Code fallback · Release {release.version}")
    """
).strip()


def _write_fixture(*, directory: Path) -> None:
    _ = (directory / "acceptance.ipynb").write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {
                    "kernelspec": {
                        "name": "python3",
                        "display_name": "Python 3",
                        "language": "python",
                    }
                },
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "frontend-review",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": _CELL,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class _Options(argparse.Namespace):
    frontend: str = ""
    port: int = 0


def main() -> None:
    """Start a locked Notebook or JupyterLab frontend on loopback."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("frontend", choices=("jupyterlab", "notebook"))
    _ = parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args(namespace=_Options())
    frontend = args.frontend
    port = args.port
    token = os.environ.get("DK_TEST_JUPYTER_TOKEN")
    if not token:
        raise SystemExit("Configure the disposable frontend test token.")
    with TemporaryDirectory(prefix="domain-kernel-browser-") as folder:
        directory = Path(folder)
        _write_fixture(directory=directory)
        result = subprocess.run(  # noqa: S603 -- selected local Python module and temporary workspace
            [
                sys.executable,
                "-m",
                frontend,
                "--no-browser",
                "--ip=127.0.0.1",
                f"--port={port}",
                f"--ServerApp.root_dir={directory}",
                "--ServerApp.port_retries=0",
                f"--IdentityProvider.token={token}",
                "--ServerApp.log_level=ERROR",
            ],
            cwd=directory,
            env={
                **os.environ,
                "PYTHONPATH": str(_ROOT),
                "JUPYTER_CONFIG_DIR": str(directory / "config"),
                "JUPYTER_DATA_DIR": str(directory / "data"),
                "JUPYTER_RUNTIME_DIR": str(directory / "runtime"),
            },
            check=False,
        )
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
