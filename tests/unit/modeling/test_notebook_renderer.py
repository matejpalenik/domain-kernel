"""Notebook inspection renders only bounded, escaped snapshots."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING

from domain_kernel import (
    ConceptDefinition,
    Definition,
    DefinitionId,
    ModelId,
    ModelScope,
    ProjectId,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


@dataclass
class _Format:
    type_printers: dict[type[object], Callable[..., object]] = field(default_factory=dict)


@dataclass
class _Display:
    formatters: dict[str, _Format]


@dataclass
class _Shell:
    display_formatter: _Display


def _concept() -> Definition:
    return Definition(
        id=DefinitionId(value="concept"),
        scope=ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model")),
        revision=4,
        name="inspected",
        display_name="<script>unsafe</script>",
        meaning="Long meaning " * 100,
        body=ConceptDefinition(),
    )


def test_bounded_notebook_summary_escapes_authored_html() -> None:
    from domain_kernel.notebook import render_notebook  # noqa: PLC0415

    output = render_notebook(value=_concept())
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in output
    assert "<script>" not in output
    assert "Revision" in output
    assert "…" in output
    assert len(output) < 1000  # noqa: PLR2004 - A deliberately oversized input must be bounded.


def test_notebook_display_registration_is_repeat_safe_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain_kernel.notebook import disable_notebook_display, enable_notebook_display  # noqa: PLC0415

    def existing(value: object, /) -> object:
        return value

    rich = _Format(type_printers={Definition: existing})
    plain = _Format()
    shell = _Shell(display_formatter=_Display(formatters={"text/html": rich, "text/plain": plain}))
    adapter = ModuleType("IPython")
    monkeypatch.setattr(adapter, "get_ipython", lambda: shell, raising=False)
    monkeypatch.setitem(sys.modules, "IPython", adapter)
    try:
        enable_notebook_display()
        replacement = rich.type_printers[Definition]
        assert replacement is not existing
        enable_notebook_display()
        assert rich.type_printers[Definition] is replacement
        assert Definition in plain.type_printers
    finally:
        disable_notebook_display()
    assert rich.type_printers == {Definition: existing}
    assert not plain.type_printers


def test_definition_page_is_bounded_and_keeps_the_cursor_private() -> None:
    from dataclasses import replace  # noqa: PLC0415

    from domain_kernel import Page, PageCursor  # noqa: PLC0415
    from domain_kernel.notebook import render_notebook  # noqa: PLC0415

    page = Page(
        items=[replace(_concept(), name=f"definition-{index:02d}") for index in range(50)],
        next_cursor=PageCursor(value="sensitive-cursor"),
    )
    output = render_notebook(value=page)
    assert "definition-00" in output
    assert "definition-49" not in output
    assert "50" in output
    assert "sensitive-cursor" not in output


def test_configuration_rendering_only_shows_the_selected_capability_summary(tmp_path: Path) -> None:
    from domain_kernel.diagnostics import (  # noqa: PLC0415
        ConfigurationReport,
        ConfigurationSetting,
        ConfigurationSource,
        DatabaseInitialization,
    )
    from domain_kernel.notebook import render_notebook  # noqa: PLC0415

    value = ConfigurationReport(
        source=ConfigurationSource.PYTHON,
        source_path=None,
        base_dir=tmp_path / "private-location",
        database_initialization=DatabaseInitialization.EXPLICIT,
        settings=(ConfigurationSetting(path=("database", "dsn"), value="private-credential"),),
        integrations=("postgresql",),
    )
    output = render_notebook(value=value)
    assert "explicit" in output
    assert "postgresql" in output
    assert "private-credential" not in output
    assert "private-location" not in output


def test_artifact_metadata_displays_link_like_values_as_escaped_text() -> None:
    from domain_kernel import Artifact, ContentHash, render_notebook  # noqa: PLC0415

    artifact = Artifact(
        project_id=ProjectId(value="project"),
        store="<svg onload=alert(1)>",
        key="javascript:alert(1)",
        content_hash=ContentHash(value=f"sha256:{'a' * 64}"),
    )
    output = render_notebook(value=artifact)
    assert "&lt;svg onload=alert(1)&gt;" in output
    assert "javascript:alert(1)" in output
    assert "href=" not in output
    assert "<svg" not in output
