"""Select an isolated path for the notebook's recruitment workspace."""

from pathlib import Path
from re import fullmatch


def select_demo_workspace(*, name: str) -> Path:
    """Select a named demo path without creating, altering or deleting data."""
    if not fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name):
        raise ValueError("Choose a demo workspace name such as recruitment or recruitment-fresh")
    path = Path("local/notebook-tour") / name
    if path.resolve() != Path.cwd().resolve() / path:
        raise ValueError("The demo workspace path must stay inside the notebook's local directory")
    return path
