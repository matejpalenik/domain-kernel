"""Cross-check authored teaching expectations without emulating SDK validation/export."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, TypeAdapter

if TYPE_CHECKING:
    from pathlib import Path

    from examples.notebooks._preview.catalogue import Catalogue, DefinitionRecord, SourceRecord
    from examples.notebooks._preview.models import Scene

MAX_VIEW_NODES = 12
SHA256_HEX_LENGTH = 64


def _unique(*, values: tuple[str, ...], label: str) -> None:
    if len(set(values)) != len(values):
        msg = f"Duplicate {label}"
        raise ValueError(msg)


def _check_definition(*, definition: DefinitionRecord, evidence_ids: set[str]) -> None:
    _unique(values=tuple(field.name for field in definition.attributes), label="attribute name")
    _unique(values=tuple(field.id for field in definition.attributes), label="attribute identity")
    field_names = {field.name for field in definition.attributes}
    if any(not set(key) <= field_names for key in definition.keys):
        msg = f"Unknown key attribute in {definition.name}"
        raise ValueError(msg)
    evidence = (
        set(definition.evidence)
        | {reference for field in definition.attributes for reference in field.evidence}
        | {reference for annotation in definition.annotations for reference in annotation.evidence}
    )
    if not evidence <= evidence_ids:
        msg = f"Unknown evidence in {definition.name}: {evidence - evidence_ids}"
        raise ValueError(msg)
    if definition.basis == "Direct source support" and not definition.evidence:
        msg = f"Missing direct support for {definition.name}"
        raise ValueError(msg)
    for field in definition.attributes:
        if field.basis == "Direct source support" and not field.evidence:
            msg = f"Missing direct field support: {definition.name}.{field.name}"
            raise ValueError(msg)
    for annotation in definition.annotations:
        if annotation.basis == "Direct source support" and not annotation.evidence:
            msg = f"Missing condition support: {definition.name}.{annotation.element}"
            raise ValueError(msg)


def _check_references(*, definitions: tuple[DefinitionRecord, ...]) -> None:
    by_name = {definition.name: definition for definition in definitions}
    for definition in definitions:
        if definition.kind == "relationship":
            for endpoint in (definition.source, definition.target):
                if endpoint not in by_name or by_name[endpoint].kind != "concept":
                    msg = f"Invalid relationship endpoint in {definition.name}"
                    raise ValueError(msg)
        for field in definition.attributes:
            if field.target is None:
                continue
            if field.target not in by_name:
                msg = f"Missing field target in {definition.name}.{field.name}"
                raise ValueError(msg)
            expected = {"structured": "structured_value", "value_set": "value_set"}
            if (
                field.value_type in expected
                and by_name[field.target].kind != expected[field.value_type]
            ):
                msg = f"Wrong field target kind in {definition.name}.{field.name}"
                raise ValueError(msg)


def check_catalogue(*, catalogue: Catalogue, sources: tuple[SourceRecord, ...]) -> None:
    """Check identities, evidence, snapshot closure and bounded views independently."""
    _unique(
        values=tuple(item.reference for item in catalogue.definitions), label="definition revision"
    )
    _unique(values=tuple(item.id for item in catalogue.snapshots), label="snapshot")
    _unique(values=tuple(item.id for item in catalogue.reviews), label="review")
    _unique(values=tuple(item.id for item in catalogue.views), label="view")
    passage_ids = tuple(passage.id for source in sources for passage in source.passages)
    _unique(values=passage_ids, label="passage identity")
    evidence_ids = set(passage_ids)
    for definition in catalogue.definitions:
        _check_definition(definition=definition, evidence_ids=evidence_ids)
    revisions = {item.reference for item in catalogue.definitions}
    reviews = {item.id for item in catalogue.reviews}
    names = {item.name for item in catalogue.definitions}
    for view in catalogue.views:
        if len(view.definitions) > MAX_VIEW_NODES or not set(view.definitions) <= names:
            msg = f"Invalid named view: {view.id}"
            raise ValueError(msg)
        _unique(values=view.definitions, label="view member")
    for snapshot in catalogue.snapshots:
        if not set(snapshot.definitions) <= revisions or not set(snapshot.reviews) <= reviews:
            msg = f"Missing snapshot reference in {snapshot.id}"
            raise ValueError(msg)
        definitions = catalogue.resolve(snapshot=snapshot.id)
        _unique(values=tuple(item.id for item in definitions), label="snapshot definition ID")
        _unique(values=tuple(item.name for item in definitions), label="snapshot definition name")
        _check_references(definitions=definitions)
        if any(
            mapping.definition not in {item.name for item in definitions}
            for mapping in snapshot.mappings
        ):
            msg = f"Mapping outside snapshot in {snapshot.id}"
            raise ValueError(msg)
    # Real legal support has acquired original-byte hashes, independently of mock results.
    for source in sources:
        if source.id in {"ai-act-en", "ai-act-fr"} and (
            source.sha256 is None
            or len(source.sha256) != SHA256_HEX_LENGTH
            or "pending" in source.verification.lower()
        ):
            msg = f"Unverified core legal source: {source.id}"
            raise ValueError(msg)


class ProjectionExcerpt(BaseModel):
    """Only the bytes needed to check the curated examples."""

    code: str


class BundleExcerpt(BaseModel):
    """Counts from the labelled inspection, not a bundle wire codec."""

    counts: dict[str, int] = Field(alias="inspection.counts")
    definitions: tuple[DefinitionExcerpt, ...] = Field(
        alias="content.definitions (selected properties)"
    )
    reviews: tuple[ReviewExcerpt, ...] = Field(alias="review decisions (selected properties)")


class DefinitionExcerpt(BaseModel):
    """Identity and revision in the illustrative bundle inventory."""

    id: str
    name: str
    kind: str
    revision: int


class ReviewExcerpt(BaseModel):
    """Selected decision properties in the curated bundle inspection."""

    id: str
    targets: tuple[str, ...]
    reason: str


class PropertyExcerpt(BaseModel):
    """One expected JSON Schema property, without emulating JSON Schema."""

    unique_items: bool = Field(default=False, alias="uniqueItems")


class SchemaExcerpt(BaseModel):
    """Selected cross-format assertions for the curated shape examples."""

    properties: dict[str, PropertyExcerpt]
    required: tuple[str, ...]


def check_projection_examples(*, catalogue: Catalogue, path: Path) -> None:
    """Compare curated JSON excerpts with the catalogue; this does not run SDK exporters."""
    projections = TypeAdapter(tuple[ProjectionExcerpt, ...]).validate_json(path.read_bytes())
    published = catalogue.resolve(snapshot="published")
    bundle = BundleExcerpt.model_validate_json(projections[0].code)
    if bundle.counts["definitions"] != len(published):
        raise ValueError("Projection inventory count differs from publication")
    expected = {(d.id, d.name, d.kind, d.revision) for d in published}
    actual = {(d.id, d.name, d.kind, d.revision) for d in bundle.definitions}
    if actual != expected or len(bundle.definitions) != len(expected):
        raise ValueError("Projection inventory revisions differ from publication")
    snapshot = next(s for s in catalogue.snapshots if s.id == "published")
    reviews = {r.id: r for r in catalogue.reviews if r.id in snapshot.reviews}
    if {r.id for r in bundle.reviews} != set(reviews) or any(
        r.targets != reviews[r.id].targets or r.reason != reviews[r.id].reason
        for r in bundle.reviews
    ):
        raise ValueError("Projection review history differs from publication")
    by_name = {item.name: item for item in published}
    for index, name in ((1, "instructions-for-use"), (5, "legal-provision")):
        schema = SchemaExcerpt.model_validate_json(projections[index].code)
        definition = by_name[name]
        if set(schema.properties) != {field.name for field in definition.attributes}:
            msg = f"Projection field drift: {name}"
            raise ValueError(msg)
        if set(schema.required) != {
            field.name for field in definition.attributes if field.required
        }:
            msg = f"Projection requiredness drift: {name}"
            raise ValueError(msg)
        for field in definition.attributes:
            projected = schema.properties[field.name]
            if field.collection == "set" and not projected.unique_items:
                msg = f"Projection collection drift: {field.name}"
                raise ValueError(msg)


def check_experiment_examples(*, scenes: tuple[Scene, ...], catalogue: Catalogue) -> None:
    """Protect the teaching distinctions that previously drifted in isolated controls."""
    chapters = {scene.id: scene for scene in scenes}
    published = {d.name: d for d in catalogue.resolve(snapshot="published")}
    acceptance = next(c for c in chapters["C2"].choices if c.id == "accept")
    if "No publication created by this decision" not in acceptance.after:
        raise ValueError("C2 experiment conflates acceptance with publication")
    projection = next(c for c in chapters["C9"].choices if c.id == "supported")
    if (
        not all(
            token in projection.before + projection.after
            for token in (
                "instructions-for-use",
                "logging-mechanisms",
                "instructions.schema.json",
                "instructions-logging-information",
            )
        )
        or "k005-1" in projection.before + projection.after
    ):
        raise ValueError("C9 experiment does not describe the current instructions projection")
    if published["legal-provision"].keys:
        raise ValueError("Removed title key returned to the published provision")
    evolution = next(c for c in chapters["C10"].choices if c.id == "extend")
    evolved = catalogue.resolve(snapshot="evolved")
    old_refs = {d.reference for d in published.values()}
    added = {d.name for d in evolved if d.reference not in old_refs}
    review = next(r for r in catalogue.reviews if set(r.targets) == added)
    if (
        f"{len(published)} definitions" not in evolution.before
        or f"{len(evolved)} definitions" not in evolution.after
        or review.id not in evolution.after
        or not all(name in evolution.after for name in added)
    ):
        raise ValueError("C10 experiment disagrees with publication differences")
    process = next(c for c in chapters["E7"].choices if c.id == "inspect")
    activities = tuple(
        row[0].removeprefix("Activity: ").casefold()
        for row in chapters["E7"].panels[0].rows
        if row[0].startswith("Activity: ")
    )
    if f"activities={len(activities)}" not in process.before or any(
        name not in process.after.casefold() for name in activities
    ):
        raise ValueError("E7 experiment differs from the domain process")
    for choice in chapters["E8"].choices:
        if (
            "InstructionsForUse" not in choice.before + choice.after
            or "LegalProvision" in choice.after
        ):
            raise ValueError("E8 experiment differs from the imported instructions schema")
    recovery = next(c for c in chapters["E9"].choices if c.id == "resume")
    recovery_tables = " ".join(
        value for panel in chapters["E9"].panels for row in panel.rows for value in row
    )
    if not all(
        token in recovery_tables and token in recovery.before + recovery.after
        for token in ("guidance-02", "case-remote-001", "case-remote-002", "case-remote-003")
    ):
        raise ValueError("E9 experiment differs from the recovery checkpoint or cases")
    logging = published["instructions-logging-information"]
    if logging.kind != "rule" or "ai-13-instructions" not in logging.evidence:
        raise ValueError("Logging qualification is not a published evidenced rule")
