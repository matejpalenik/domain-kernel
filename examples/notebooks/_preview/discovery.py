"""Authored prompt captures for one lesson, not an extractor or mock SDK."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Literal

from examples.notebooks._preview.catalogue import FrozenRecord, load_catalogue, load_sources
from examples.notebooks._preview.models import Panel
from examples.notebooks._preview.rendering import render_table


class PromptExample(FrozenRecord):
    """A fixed example of the instructions and inputs captured for a discovery run."""

    id: Literal["default", "additional", "override"]
    title: str
    additional_instructions: str | None
    prompt_override: str | None
    default_prompt_version: str | None
    effective_instructions: str
    response_schema_version: str
    source_ids: tuple[str, ...]
    candidate_names: tuple[str, ...]
    interpretation: str


class DiscoveryLesson(FrozenRecord):
    """Shared text and curated outcomes, with no provider execution."""

    default_instructions: str
    default_prompt_version: str
    response_schema_version: str
    recruitment_focus: str
    documentation_focus: str
    examples: tuple[PromptExample, ...]


def load_discovery_lesson() -> DiscoveryLesson:
    """Read local, immutable teaching examples."""
    path = Path(__file__).parents[1] / "fixtures" / "discovery-prompts.json"
    return DiscoveryLesson.model_validate_json(path.read_bytes())


def check_discovery_lesson(*, lesson: DiscoveryLesson) -> None:
    """Check fixture consistency, not SDK inference or prompt effectiveness."""
    names = {definition.name for definition in load_catalogue().definitions}
    sources = {source.id for source in load_sources()}
    for example in lesson.examples:
        if example.prompt_override is not None:
            expected = example.prompt_override
            version = None
        else:
            expected = lesson.default_instructions
            version = lesson.default_prompt_version
            if example.additional_instructions is not None:
                expected += "\n\nAdditional instructions:\n" + example.additional_instructions
        if (example.effective_instructions, example.default_prompt_version) != (expected, version):
            message = f"Prompt precedence differs in {example.id}"
            raise ValueError(message)
        if example.response_schema_version != lesson.response_schema_version:
            message = f"Output contract differs in {example.id}"
            raise ValueError(message)
        if not set(example.candidate_names) <= names or not set(example.source_ids) <= sources:
            message = f"Unknown proposal or evidence in {example.id}"
            raise ValueError(message)
        if example.additional_instructions not in (None, lesson.recruitment_focus):
            message = f"Recruitment focus differs in {example.id}"
            raise ValueError(message)
        if example.prompt_override not in (None, lesson.documentation_focus):
            message = f"Documentation focus differs in {example.id}"
            raise ValueError(message)


def render_discovery_example(*, example_id: str) -> str:
    """Show captured instructions and illustrative proposals with a static alternative."""
    lesson = load_discovery_lesson()
    example = next(item for item in lesson.examples if item.id == example_id)
    ignored = "Default and additional instructions ignored" if example.prompt_override else "None"
    panel = Panel(
        title=example.title,
        columns=("Inspect", "Simulated capture"),
        rows=(
            ("Evidence revisions", ", ".join(example.source_ids) + " — unchanged full inputs"),
            ("Instruction mode", example.id),
            ("Ignored instructions", ignored),
            ("Default version", example.default_prompt_version or "Not used"),
            ("SDK-owned output schema", example.response_schema_version),
            ("Illustrative pending meanings", ", ".join(example.candidate_names)),
        ),
        note=example.interpretation,
    )
    return (
        '<section class="dk-preview"><div class="dk-eyebrow">Simulated prompt capture</div>'
        + render_table(panel=panel)
        + "<details><summary>Inspect the effective instructions</summary><pre>"
        + escape(example.effective_instructions)
        + "</pre></details><p class='dk-note'>Authored request/result illustration. The preview "
        "versions identify fixtures, not released SDK prompts or schemas. Candidate selections "
        "are teaching expectations, not measured extraction results. Existing failure and recovery "
        "rules apply in every mode.</p></section>"
    )
