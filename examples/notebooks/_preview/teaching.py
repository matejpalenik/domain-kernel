"""Read-only teaching views over the shared, explicitly authored catalogue."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from examples.notebooks._preview.models import Panel
from examples.notebooks._preview.rendering import render_table

if TYPE_CHECKING:
    from examples.notebooks._preview.catalogue import DefinitionRecord, FieldRecord
    from examples.notebooks._preview.models import Scene


def _instructions(*, scene: Scene) -> DefinitionRecord:
    return next(item for item in scene.definitions if item.name == "instructions-for-use")


def _field(*, scene: Scene, name: str) -> FieldRecord:
    field = next(
        (item for item in _instructions(scene=scene).attributes if item.name == name), None
    )
    if field is None:
        msg = f"Unknown instructions field: {name}"
        raise ValueError(msg)
    return field


def render_destination(*, scene: Scene) -> str:
    """A bounded look ahead, without advancing the tutorial's canonical model."""
    definition = _instructions(scene=scene)
    field = _field(scene=scene, name="logging-mechanisms")
    rule = next(d for d in scene.definitions if d.name == "instructions-logging-information")
    return (
        '<section class="dk-preview"><div class="dk-eyebrow">'
        "YOUR DESTINATION · SIMULATED 1.1.0</div>"
        '<h2>A contract your application can inspect</h2><div class="dk-split">'
        '<article class="dk-evidence"><h3>Find the shape</h3>'
        f"<p>{escape(definition.display_name)} · revision {definition.revision}</p>"
        f"<pre>{escape(field.name)}\nrequired = {field.required}\n"
        f"collection = {field.collection}</pre>"
        "<p>Use a stable field identity in a form, extraction target or catalogue.</p></article>"
        '<article class="dk-evidence"><h3>Keep the qualification</h3>'
        f"<p><code>{escape(rule.name)}</code></p><p>{escape(rule.meaning)}</p>"
        f"<p>Supporting passage: {escape(', '.join(rule.evidence))}</p></article></div>"
        '<p class="dk-note">A look ahead at a fixed publication. Your working model has not '
        "been created yet. Application behaviour and applicability decisions remain downstream.</p>"
        "</section>"
    )


def render_authoring_stage(*, scene: Scene, stage: str) -> str:
    """Describe the staged seed operation using its single definition catalogue."""
    stages = {
        "draft": ("Draft plan", "Proposed definitions only; accepted additions=0; publications=0."),
        "impact": ("Impact inspected", "case-001 · Accept preview; submitted decisions=0."),
        "accepted": ("Decision submitted", "case-001 · accepted by demo:reviewer; publications=0."),
    }
    title, note = stages[stage]
    panel = Panel(
        title=f"{title} · {len(scene.definitions)} definitions",
        columns=("Name", "Kind", "Meaning"),
        rows=tuple((d.name, d.kind, d.meaning) for d in scene.definitions),
        note=note,
    )
    return (
        '<section class="dk-preview"><div class="dk-eyebrow">SCRIPTED SAMPLE · C2</div>'
        + render_table(panel=panel)
        + "<p>Draft → inspected impact → accepted working model → published snapshot.</p></section>"
    )


def render_review_comparison(*, scene: Scene) -> str:
    """Compare the two meanings before the separately scripted rejection."""
    definitions = {d.name: d for d in scene.definitions}
    return (
        '<section class="dk-preview"><div class="dk-eyebrow">PENDING DECISION · C6</div>'
        + render_table(
            panel=Panel(
                title="Would these meanings be interchangeable?",
                columns=("Definition", "Meaning"),
                rows=tuple(
                    (definitions[name].display_name, definitions[name].meaning)
                    for name in ("recruitment-ai-system", "high-risk-recruitment-ai-system")
                ),
                note=(
                    "case-007 · Reject preview: keep the distinction; no accepted definition "
                    "changes. No decision has been submitted by inspecting this comparison."
                ),
            )
        )
        + "</section>"
    )


def render_requirement_trace(*, scene: Scene) -> str:
    """Follow the actual curated correction and refinement through the published snapshot."""
    definition = _instructions(scene=scene)
    logging = _field(scene=scene, name="logging-mechanisms")
    source = next(item for item in scene.source_records if item.id == "ai-act-en")
    passage = next(item for item in source.passages if item.id == "ai-13-instructions")
    rejection = next(item for item in scene.reviews if item.id == "case-008")
    refinement = next(item for item in scene.reviews if item.id == "case-009")
    rule = next(d for d in scene.definitions if d.name == "instructions-logging-information")
    steps = (
        ("C3 · Evidence", "Read the provision", passage.locator, "source"),
        (
            "C4 · Proposal",
            "A plausible mistake",
            "Proposed merge of instructions and technical documentation.",
            "pending",
        ),
        (
            "C6 · Review",
            "Rejected conflation",
            f"{rejection.id}: keep the two document meanings separate.",
            "review",
        ),
        (
            "C7 / C8 · Contract",
            "Preserve the condition",
            (
                f"{refinement.id}: add {logging.name} as an optional field; "
                f"publish revision {definition.revision}."
            ),
            "accepted",
        ),
        (
            "C9 · Consumer",
            "Reuse with its limits",
            "The shape accepts absence. The host must still interpret relevance.",
            "consumer",
        ),
    )
    cards = "".join(
        f'<li class="dk-stage dk-stage-{kind}"><span class="dk-step">{index:02}</span>'
        f'<div class="dk-eyebrow">{escape(chapter)}</div><h3>{escape(title)}</h3>'
        f"<p>{escape(description)}</p></li>"
        for index, (chapter, title, description, kind) in enumerate(steps, start=1)
    )
    return (
        '<section class="dk-preview dk-worked">'
        '<div class="dk-eyebrow">ONE REQUIREMENT, END TO END</div>'
        '<h2>What survived the journey?</h2><p class="dk-lead">The value is the distinction you '
        "preserved: instructions stay separate from technical documentation, and a conditional "
        "information requirement stays conditional.</p>"
        '<span class="dk-badge">Simulated review and publication</span>'
        f'<ol class="dk-stages" aria-label="Evidence to consumer journey">{cards}</ol>'
        '<div class="dk-split"><article class="dk-evidence"><div class="dk-eyebrow">SOURCE</div>'
        f"<h3>{escape(passage.id)}</h3><p>{escape(passage.text)}</p>"
        f'<p class="dk-note">{escape(passage.kind)} · {escape(source.edition)}</p>'
        f'<a href="{escape(source.url, quote=True)}" target="_blank" rel="noopener noreferrer">'
        f"Read {escape(passage.locator)}</a></article>"
        '<article class="dk-evidence"><div class="dk-eyebrow">REVIEWED CONTRACT</div>'
        f"<h3><code>{escape(logging.name)}</code></h3><p>{escape(logging.meaning)}</p>"
        f'<p class="dk-qualification"><strong>Qualification retained:</strong> '
        f"{escape(rule.meaning)}</p><p>"
        f"Published descriptive rule: <code>{escape(rule.name)}</code>. "
        f"{escape(logging.basis)} · {escape(logging.id)} · revision {definition.revision}</p>"
        '<p class="dk-note">Curated export expectation: a string property, absent from the '
        "root required list. This presentation is not an SDK exporter.</p></article></div>"
        "<details><summary>Inspect the attributed decisions behind this example</summary>"
        + render_table(
            panel=Panel(
                title="Two distinct decisions",
                columns=("Case / action", "Actor", "Reason"),
                rows=tuple(
                    (f"{r.id} / {r.action}", r.actor, r.reason) for r in (rejection, refinement)
                ),
            )
        )
        + '</details><p class="dk-note">The proposed merge was rejected; it was never a published '
        "definition. The logging field was added during refinement, not silently inserted into "
        "the earlier snapshot.</p></section>"
    )


def render_consumer_field(*, scene: Scene, name: str) -> str:
    """Inspect one field without a producer workspace or fabricated compliance result."""
    definition = _instructions(scene=scene)
    field = _field(scene=scene, name=name)
    required = "Required" if field.required else "Optional"
    links = "".join(
        f"<li><strong>{escape(passage.locator)}</strong> · {escape(passage.kind)}<br>"
        f'<a href="{escape(source.url, quote=True)}" target="_blank" rel="noopener noreferrer">'
        f"{escape(source.title)} · {escape(passage.id)}</a></li>"
        for source in scene.source_records
        for passage in source.passages
        if passage.id in field.evidence
    )
    shape = field.value_type + (f" → {field.target}" if field.target else "")
    qualification = field.qualification or (
        "This capture shape does not prescribe the adequacy of the supplied information."
    )
    rules = render_table(
        panel=Panel(
            title="Published descriptive rules selected by the consumer",
            columns=("Name", "Meaning", "Evidence"),
            rows=tuple(
                (item.name, item.meaning, ", ".join(item.evidence))
                for item in scene.definitions
                if item.name
                in {
                    "instructions-logging-information",
                    "documentation-distinction",
                    "deployer-log-retention",
                }
            ),
            note=(
                "The consumer selects these names explicitly. Their presence does not "
                "establish applicability to a particular organisation."
            ),
        )
    )
    return (
        '<section class="dk-preview dk-consumer">'
        '<div class="dk-eyebrow">READ-ONLY CONSUMER INSPECTION</div>'
        f'<h2>{escape(field.name)}</h2><p class="dk-note">Simulated published result · '
        f"{escape(scene.snapshot)} · {escape(definition.id)}@{definition.revision}</p>"
        '<div class="dk-metrics">'
        f"<div><span>Shape</span><strong>{escape(shape)}</strong></div>"
        f"<div><span>Presence</span><strong>{required}</strong></div>"
        f"<div><span>Collection</span><strong>{escape(field.collection)}</strong></div></div>"
        f'<p class="dk-lead">{escape(field.meaning)}</p>'
        '<div class="dk-split"><article class="dk-evidence">'
        "<h3>What your application can reuse</h3>"
        f"<p>Stable field identity: <code>{escape(field.id)}</code>.</p>"
        "<p>Use the published shape for a documentation form, a typed extraction target or a "
        "catalogue entry. Retrieve the separate instructions-logging-information rule for "
        "the logging condition and its source evidence.</p>"
        f'<p class="dk-note">Modelling basis: {escape(field.basis)}</p></article>'
        '<article class="dk-evidence"><h3>Teaching commentary: what remains a judgement</h3>'
        f'<p class="dk-qualification">{escape(qualification)}</p>'
        "<p>Schema validity does not establish legal completeness. A host decides which "
        "conditions apply and whether the supplied information is adequate.</p></article></div>"
        f'<h3>Evidence available for inspection</h3><ul class="dk-citations">{links}</ul>'
        "<details open><summary>Read the published descriptive rules</summary>"
        f"{rules}</details>"
        '<p class="dk-note">The bundle carries citation records. These excerpt annotations come '
        "from the notebook source ledger; loading a bundle does not fetch source text. "
        "Field-level basis and qualifications are teaching annotations over the existing "
        "definitions, not additional AttributeDefinition properties.</p></section>"
    )
