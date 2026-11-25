"""Source catalogue for the pinned public evidence used in the examples."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter


class FrozenRecord(BaseModel):
    """Validate and freeze the local source manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")


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


def load_sources() -> tuple[SourceRecord, ...]:
    """Load source facts without requesting original documents."""
    return TypeAdapter(tuple[SourceRecord, ...]).validate_json(
        (Path(__file__).parents[1] / "fixtures" / "sources.json").read_bytes()
    )
