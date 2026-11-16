"""Small immutable presentation fixtures and bounded experiment branches, not an SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from examples.notebooks._preview.catalogue import (
    Catalogue,
    DefinitionRecord,
    FrozenRecord,
    MappingRecord,
    ReviewRecord,
    SourceRecord,
    ViewRecord,
    load_catalogue,
    load_sources,
)


class Panel(FrozenRecord):
    """A bounded, accessible table and its teaching note."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    note: str = ""


class Node(FrozenRecord):
    """A labelled node in the small authored model diagram."""

    id: str
    label: str
    kind: str = "concept"


class Edge(FrozenRecord):
    """A directed connection with an explicit semantic role."""

    source: str
    target: str
    label: str
    kind: str = "domain relationship"


class Choice(FrozenRecord):
    """One curated experiment outcome; no general domain rule evaluation."""

    id: str
    label: str
    before: str
    after: str
    explanation: str
    blocked: bool = False
    reason: str = ""
    interaction: Literal["action", "inspect"] = "action"


class Scene(FrozenRecord):
    """A canonical chapter snapshot, independent of interactive branches."""

    id: str
    title: str
    snapshot: str
    summary: str
    expected: str
    owners: tuple[str, ...]
    sources: tuple[str, ...]
    panels: tuple[Panel, ...]
    choices: tuple[Choice, ...]
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    catalogue_snapshot: str | None = None
    definitions: tuple[DefinitionRecord, ...] = ()
    views: tuple[ViewRecord, ...] = ()
    mappings: tuple[MappingRecord, ...] = ()
    reviews: tuple[ReviewRecord, ...] = ()
    source_records: tuple[SourceRecord, ...] = ()


def _refinement_panel(*, catalogue: Catalogue, definitions: tuple[DefinitionRecord, ...]) -> Panel:
    """Compare field revisions without maintaining an independent before/after fixture."""
    before = {d.name: d for d in catalogue.resolve(snapshot="reconciled")}
    changes: list[tuple[str, ...]] = []
    for definition in definitions:
        if definition.name not in {"instructions-for-use", "legal-provision"}:
            continue
        previous = before[definition.name]
        old_fields = {f.name: f for f in previous.attributes}
        for attribute in definition.attributes:
            status = "Unchanged" if old_fields.get(attribute.name) == attribute else "Added"
            changes.append(
                (
                    status,
                    definition.name,
                    attribute.name,
                    "required" if attribute.required else "optional",
                )
            )
        if previous.keys != definition.keys:
            changes.append(("Removed", definition.name, "provision-identity", "unsafe title key"))
    return Panel(
        title="Inspect the field changes",
        columns=("Change", "Definition", "Field / key", "Presence / reason"),
        rows=tuple(sorted(changes, key=lambda row: row[0] == "Unchanged")),
        note="Added and removed elements appear first; unchanged fields retain their identities.",
    )


def load_scenes() -> tuple[Scene, ...]:
    """Load and freeze the small local fixtures without fetching sources."""
    path = Path(__file__).parents[1] / "fixtures" / "scenes.json"
    scenes = TypeAdapter(tuple[Scene, ...]).validate_json(path.read_bytes())
    catalogue = load_catalogue()
    sources = load_sources()
    snapshots = {item.id: item for item in catalogue.snapshots}
    reviews = {item.id: item for item in catalogue.reviews}
    result: list[Scene] = []
    for scene in scenes:
        if scene.catalogue_snapshot is None:
            result.append(scene)
            continue
        definitions = catalogue.resolve(snapshot=scene.catalogue_snapshot)
        nodes = tuple(
            Node(id=item.name, label=item.display_name, kind=item.kind)
            for item in definitions
            if item.kind != "relationship"
        )
        edges = tuple(
            Edge(source=item.source, target=item.target, label=item.display_name)
            for item in definitions
            if item.source is not None and item.target is not None
        )
        snapshot = snapshots[scene.catalogue_snapshot]
        selected_reviews = tuple(reviews[key] for key in snapshot.reviews)
        panels = list(scene.panels)
        choices = scene.choices
        if scene.id in {"C6", "C8", "C10"}:
            panels.append(
                Panel(
                    title="Attributed decisions behind this snapshot",
                    columns=("Case", "Action", "Actor", "Reason"),
                    rows=tuple(
                        (item.id, item.action, item.actor, item.reason) for item in selected_reviews
                    ),
                )
            )
        if scene.id == "C6":
            documents = tuple(
                d
                for d in definitions
                if d.name in {"instructions-for-use", "technical-documentation"}
            )
            panels.append(
                Panel(
                    title="Keep the two document meanings separate",
                    columns=("Rejected proposal", "Reviewed definition", "Preserved meaning"),
                    rows=tuple(
                        ("Merge both documents", d.display_name, d.meaning) for d in documents
                    ),
                    note="case-008 rejects the merge; case-006 retains the separate definitions.",
                )
            )
            panels.append(
                Panel(
                    title="Reviewed reference mappings",
                    columns=("Local definition", "Relation", "Original IRI", "Decision"),
                    rows=tuple(
                        (item.definition, item.relation, item.iri, item.decision)
                        for item in snapshot.mappings
                    ),
                    note=(
                        "These are business mappings. Formal semantic assertions require "
                        "their own reviewed operation."
                    ),
                )
            )
        if scene.id == "C7":
            panels.append(_refinement_panel(catalogue=catalogue, definitions=definitions))
        if scene.id == "C10":
            previous_content = catalogue.resolve(snapshot="published")
            previous_refs = {item.reference for item in previous_content}
            added = tuple(item.name for item in definitions if item.reference not in previous_refs)
            evolution = next(item for item in selected_reviews if set(item.targets) == set(added))
            facts = {
                "published_count": len(previous_content),
                "published_relationships": sum(d.kind == "relationship" for d in previous_content),
                "evolved_count": len(definitions),
                "evolved_relationships": len(edges),
                "evolution_case": evolution.id,
                "evolution_additions": ", ".join(added),
            }
            choices = tuple(
                choice.model_copy(
                    update={
                        "before": choice.before.format_map(facts),
                        "after": choice.after.format_map(facts),
                    }
                )
                for choice in scene.choices
            )
            comparisons: list[tuple[str, ...]] = []
            for version, key in (("1.0.0", "seed"), ("1.1.0", "published"), ("1.2.0", "evolved")):
                content = catalogue.resolve(snapshot=key)
                relationships = sum(item.kind == "relationship" for item in content)
                comparisons.append(
                    (
                        version,
                        str(len(content)),
                        str(relationships),
                        str(len(content) - relationships),
                    )
                )
            panels.append(
                Panel(
                    title="Immutable publication comparison",
                    columns=("Version", "All definitions", "Relationships", "Other definitions"),
                    rows=tuple(comparisons),
                )
            )
            previous = {item.reference for item in catalogue.resolve(snapshot="published")}
            additions = tuple(item.name for item in definitions if item.reference not in previous)
            panels.append(
                Panel(
                    title="Compared definition revisions",
                    columns=("Change", "Result"),
                    rows=(
                        ("Added", ", ".join(additions)),
                        ("Previously published revisions preserved", str(len(previous))),
                    ),
                )
            )
        result.append(
            scene.model_copy(
                update={
                    "definitions": definitions,
                    "choices": choices,
                    "nodes": nodes,
                    "edges": edges,
                    "views": catalogue.views,
                    "mappings": snapshot.mappings,
                    "reviews": selected_reviews,
                    "panels": tuple(panels),
                    "source_records": sources,
                }
            )
        )
    return tuple(result)


class ExperimentStatus(StrEnum):
    """Visible state of a preview experiment, never an SDK status."""

    DRAFT = "Draft experiment"
    PREVIEWED = "Impact inspected"
    APPLIED = "Sample action applied"
    BLOCKED = "Sample action blocked"


@dataclass(kw_only=True)
class Experiment:
    """Try predefined alternatives without modifying the canonical scene."""

    scene: Scene
    status: ExperimentStatus = field(default=ExperimentStatus.DRAFT, init=False)
    submissions: int = field(default=0, init=False)
    choice_id: str = field(default="", init=False)
    reason: str = field(default="", init=False)
    _inspected: tuple[str, str] | None = field(default=None, init=False)
    _result: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Start with the first curated alternative."""
        self.choice_id = self.scene.choices[0].id

    @property
    def choice(self) -> Choice:
        """Return the selected immutable alternative."""
        return next(choice for choice in self.scene.choices if choice.id == self.choice_id)

    def choose(self, *, choice_id: str) -> None:
        """Changing intent invalidates the prior impact preview."""
        if choice_id not in {choice.id for choice in self.scene.choices}:
            raise ValueError("Select one of this chapter's named sample alternatives.")
        if choice_id != self.choice_id:
            self.choice_id = choice_id
            self.invalidate()

    def invalidate(self) -> None:
        """Discard inspected intent after a control changes."""
        self._inspected = None
        self._result = None
        self.status = ExperimentStatus.DRAFT

    def preview(self, *, reason: str) -> Choice:
        """Inspect a selected sample outcome before explicit submission."""
        if self.choice.interaction == "inspect":
            raise ValueError("This is read-only inspection; no decision or reason is required.")
        if not reason.strip():
            raise ValueError("Enter a reason before previewing this sample action.")
        self.reason = reason.strip()
        intent = (self.choice_id, self.reason)
        if intent != self._inspected:
            self._result = None
            self._inspected = intent
            self.status = ExperimentStatus.PREVIEWED
        return self.choice

    def submit(self) -> str:
        """Apply an inspected sample transition once; never touch SDK state."""
        if self.choice.interaction == "inspect":
            raise ValueError("Read-only inspection cannot submit a decision.")
        if self._inspected != (self.choice_id, self.reason):
            raise ValueError("Preview this exact sample action before submitting it.")
        if self._result is not None:
            return self._result
        choice = self.choice
        if choice.blocked:
            self.status = ExperimentStatus.BLOCKED
        else:
            self.status = ExperimentStatus.APPLIED
            self.submissions += 1
        self._result = choice.after
        return self._result

    def reset(self) -> None:
        """Reset only this in-memory experiment after an explicit request."""
        self.choice_id = self.scene.choices[0].id
        self.reason = ""
        self.submissions = 0
        self.invalidate()
