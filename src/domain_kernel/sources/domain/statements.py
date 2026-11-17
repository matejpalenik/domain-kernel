"""Attributed statement capture records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, unique
from typing import Literal

from domain_kernel.shared.identifiers.person_id import PersonId
from domain_kernel.shared.validation import require_exact, require_text


@unique
class StatementForm(StrEnum):
    """How the speaker's content was represented."""

    QUOTATION = "quotation"
    SUMMARY = "summary"


@unique
class StatementIntent(StrEnum):
    """What the speaker intended to communicate."""

    OBSERVATION = "observation"
    PROPOSAL = "proposal"
    ASSERTION = "assertion"


@dataclass(frozen=True, kw_only=True)
class Person:
    """The host-supplied identity and role of a speaker."""

    id: PersonId
    name: str
    role: str

    def __post_init__(self) -> None:
        """Require nominal identity and nonblank attribution."""
        require_exact(value=self.id, expected=PersonId, field="Person ID")
        require_text(value=self.name, field="Person name")
        require_text(value=self.role, field="Person role")


@dataclass(frozen=True, kw_only=True)
class StatementOrigin:
    """The resolved attribution of one captured statement."""

    speaker: Person
    recorded_by: str
    stated_at: datetime | None
    recorded_at: datetime
    context: str
    form: StatementForm
    intent: StatementIntent
    payload_schema_version: Literal[1] = 1
    kind: Literal["statement"] = "statement"

    def __post_init__(self) -> None:
        """Validate capture provenance independently of statement text."""
        require_exact(value=self.speaker, expected=Person, field="Statement speaker")
        require_text(value=self.recorded_by, field="Statement recorder")
        require_text(value=self.context, field="Statement context")
        require_exact(value=self.form, expected=StatementForm, field="Statement form")
        require_exact(value=self.intent, expected=StatementIntent, field="Statement intent")
        require_exact(value=self.payload_schema_version, expected=int, field="Statement version")
        require_exact(value=self.kind, expected=str, field="Statement origin kind")
        if self.kind != "statement" or self.payload_schema_version != 1:
            raise ValueError("Use the supported statement origin and payload version")
        require_statement_time(value=self.recorded_at)
        if self.stated_at is not None:
            require_statement_time(value=self.stated_at)


def require_statement_time(*, value: datetime) -> None:
    """Require an attributed instant without supplying a default original time."""
    require_exact(value=value, expected=datetime, field="Statement time")
    if value.utcoffset() is None:
        raise ValueError("Supply a timezone-aware statement time.")


@dataclass(frozen=True, kw_only=True)
class StatementPayload:
    """The explicitly recorded primary text and its attribution."""

    text: str = field(repr=False)
    origin: StatementOrigin

    def __post_init__(self) -> None:
        """Validate detached attributed text."""
        require_text(value=self.text, field="Statement text")
        require_exact(value=self.origin, expected=StatementOrigin, field="Statement origin")
