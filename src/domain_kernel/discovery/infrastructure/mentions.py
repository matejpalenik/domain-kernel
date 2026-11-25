"""Optional host-owned named entity hints for omission checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, TypeAdapter

from domain_kernel.shared.validators.text_validation import TextValidation

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


DEFAULT_MENTION_LABELS = (
    "actor or role",
    "organization",
    "artifact or record",
    "process or event",
    "resource",
    "measure",
)


class EntityMention(BaseModel):
    """A candidate span at zero-based offsets in the original passage."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="ignore", frozen=True)
    label: str
    text: str
    start: int
    end: int


@dataclass(frozen=True, kw_only=True)
class NamedEntityHints:
    """Adapt a local GLiNER-compatible predictor with a versioned label profile."""

    predict: Callable[[str, list[str]], object]
    profile: str
    labels: Sequence[str] = DEFAULT_MENTION_LABELS

    def __post_init__(self) -> None:
        """Detach labels and require an explicit identifier for the local model and rules."""
        if not self.profile.strip() or isinstance(self.labels, (str, bytes)) or not self.labels:
            raise ValueError("Supply a versioned NER profile and a collection of labels.")
        for label in self.labels:
            TextValidation.require_text(value=label, field="NER label")
        object.__setattr__(self, "labels", tuple(self.labels))

    def __call__(self, text: str) -> list[EntityMention]:
        """Keep exact mentions under the selected labels."""
        mentions = _MENTIONS.validate_python(self.predict(text, list(self.labels)))
        return [
            m
            for m in mentions
            if m.label in self.labels
            and 0 <= m.start < m.end <= len(text)
            and text[m.start : m.end] == m.text
        ]


_MENTIONS = TypeAdapter(list[EntityMention])
