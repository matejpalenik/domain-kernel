"""Immutable teaching records, deliberately smaller than the planned SDK contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter


class FrozenRecord(BaseModel):
    """Validate and freeze the local preview boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")


type Basis = Literal[
    "Direct source support", "Inferred modelling structure", "Application-authored choice"
]


class Passage(FrozenRecord):
    """A verified selection or explicitly qualified source paraphrase."""

    id: str
    locator: str
    text: str
    kind: str


class SourceRecord(FrozenRecord):
    """Acquisition facts are independent of simulated parser results."""

    id: str
    title: str
    classification: str
    edition: str
    url: str
    sha256: str | None
    verification: str
    attribution: str
    passages: tuple[Passage, ...]


class FieldRecord(FrozenRecord):
    """Selected inspected attribute properties, not an SDK wire format."""

    id: str
    name: str
    value_type: str
    required: bool = False
    collection: str = "single"
    target: str | None = None
    meaning: str
    qualification: str = ""
    basis: Basis
    evidence: tuple[str, ...] = ()


class MeaningAnnotation(FrozenRecord):
    """A teaching annotation on one descriptive rule condition or design choice."""

    element: str
    meaning: str
    basis: Basis
    evidence: tuple[str, ...] = ()


class DefinitionRecord(FrozenRecord):
    """An authored expected definition at an explicit revision."""

    id: str
    name: str
    display_name: str
    kind: str
    revision: int = 1
    meaning: str
    basis: Basis
    evidence: tuple[str, ...]
    attributes: tuple[FieldRecord, ...] = ()
    keys: tuple[tuple[str, ...], ...] = ()
    members: tuple[tuple[str, str], ...] = ()
    details: tuple[tuple[str, str], ...] = ()
    annotations: tuple[MeaningAnnotation, ...] = ()
    source: str | None = None
    target: str | None = None

    @property
    def reference(self) -> str:
        """Identify this fixture revision without creating an SDK identifier."""
        return f"{self.id}@{self.revision}"


class MappingRecord(FrozenRecord):
    """A reviewed business alignment; never an implicit OWL assertion."""

    definition: str
    relation: str
    iri: str
    decision: str
    explanation: str


class ReviewRecord(FrozenRecord):
    """A concrete authored review outcome with attribution."""

    id: str
    action: str
    targets: tuple[str, ...]
    actor: str
    reason: str


class ViewRecord(FrozenRecord):
    """A small authored viewport, independent of the full model size."""

    id: str
    title: str
    definitions: tuple[str, ...]


class SnapshotRecord(FrozenRecord):
    """An immutable selection of reviewed definition revisions."""

    id: str
    definitions: tuple[str, ...]
    reviews: tuple[str, ...]
    mappings: tuple[MappingRecord, ...] = ()


class Catalogue(FrozenRecord):
    """Shared expected content used by all chapter presentations."""

    definitions: tuple[DefinitionRecord, ...]
    snapshots: tuple[SnapshotRecord, ...]
    views: tuple[ViewRecord, ...]
    reviews: tuple[ReviewRecord, ...]

    def resolve(self, *, snapshot: str) -> tuple[DefinitionRecord, ...]:
        """Resolve only explicit local fixture references; never infer model changes."""
        record = next(item for item in self.snapshots if item.id == snapshot)
        definitions = {item.reference: item for item in self.definitions}
        return tuple(definitions[reference] for reference in record.definitions)


def load_catalogue() -> Catalogue:
    """Read the authored catalogue once at the preview boundary."""
    return Catalogue.model_validate_json(
        (Path(__file__).parents[1] / "fixtures" / "catalogue.json").read_bytes()
    )


def load_sources() -> tuple[SourceRecord, ...]:
    """Load source facts without requesting original documents."""
    return TypeAdapter(tuple[SourceRecord, ...]).validate_json(
        (Path(__file__).parents[1] / "fixtures" / "sources.json").read_bytes()
    )
