"""Immutable value contracts shared across domain contexts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.discovery.domain.identifiers.candidate_id import CandidateId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.reference_packs.domain.identifiers.reference_definition_id import (
    ReferenceDefinitionId,
)
from domain_kernel.shared.enums.issue_severity import IssueSeverity
from domain_kernel.shared.identifiers.content_hash import ContentHash
from domain_kernel.shared.identifiers.page_cursor import PageCursor
from domain_kernel.shared.validation import is_non_string_sequence, require_exact

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True)
class Count:
    """Nonnegative exact integer value used for bounded counts."""

    value: int

    def __post_init__(self) -> None:
        """Reject booleans, non-integers, and negative counts."""
        if type(self.value) is not int:
            raise TypeError("Count value must be an exact integer")
        if self.value < 0:
            raise ValueError("Count value must be nonnegative")


@dataclass(frozen=True, kw_only=True, init=False)
class Issue:
    """Sanitized diagnostic attached to validation and typed failures."""

    code: str
    path: tuple[str | int, ...]
    message: str
    severity: IssueSeverity

    def __init__(
        self,
        *,
        code: str,
        path: Sequence[str | int],
        message: str,
        severity: IssueSeverity = IssueSeverity.ERROR,
    ) -> None:
        """Validate fields and snapshot the caller-owned path."""
        if type(code) is not str:
            raise TypeError("Issue code must be a string")
        if not code:
            raise ValueError("Issue code must be a nonempty string")
        if type(message) is not str:
            raise TypeError("Issue message must be a string")
        if not message:
            raise ValueError("Issue message must be a nonempty string")
        if not is_non_string_sequence(path):
            raise TypeError("Issue path must be a sequence of strings and integers")
        if type(severity) is not IssueSeverity:
            raise TypeError("Issue severity must be an IssueSeverity member")

        path_snapshot = tuple(path)
        if any(type(part) not in (str, int) for part in path_snapshot):
            raise TypeError("Issue path elements must be exact strings or integers")

        object.__setattr__(self, "code", code)
        object.__setattr__(self, "path", path_snapshot)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "severity", severity)


@dataclass(frozen=True, kw_only=True)
class ModelScope:
    """Project and model identity used to scope operations and references."""

    project_id: ProjectId
    model_id: ModelId

    def __post_init__(self) -> None:
        """Require the nominal project and model identity types."""
        if type(self.project_id) is not ProjectId:
            raise TypeError("ModelScope project_id must be a ProjectId")
        if type(self.model_id) is not ModelId:
            raise TypeError("ModelScope model_id must be a ModelId")


@dataclass(frozen=True, kw_only=True)
class ModelVersion:
    """Immutable version identity for a model snapshot."""

    scope: ModelScope
    version: str
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the exact scope, label, and content digest types."""
        if type(self.scope) is not ModelScope:
            raise TypeError("ModelVersion scope must be a ModelScope")
        if type(self.version) is not str:
            raise TypeError("ModelVersion version must be a string")
        if not self.version:
            raise ValueError("ModelVersion version must be a nonempty string")
        if type(self.content_hash) is not ContentHash:
            raise TypeError("ModelVersion content_hash must be a ContentHash")


@dataclass(frozen=True, kw_only=True)
class CandidatePin:
    """Reference to an exact compiled model snapshot."""

    scope: ModelScope
    candidate_id: CandidateId
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Keep candidate, scope and content hash nominally distinct."""
        require_exact(value=self.scope, expected=ModelScope, field="Candidate scope")
        require_exact(value=self.candidate_id, expected=CandidateId, field="Candidate identity")
        require_exact(value=self.content_hash, expected=ContentHash, field="Candidate hash")


type SnapshotReference = ModelVersion | CandidatePin


@dataclass(frozen=True, kw_only=True)
class PinnedDefinitionReference:
    """Definition identity pinned to one exact immutable model version."""

    model: ModelVersion
    definition_id: DefinitionId
    definition_revision: int
    kind: Literal["pinned_definition"] = "pinned_definition"

    def __post_init__(self) -> None:
        """Enforce exact types, positive revision, and fixed discriminator."""
        if type(self.model) is not ModelVersion:
            raise TypeError("PinnedDefinitionReference model must be a ModelVersion")
        if type(self.definition_id) is not DefinitionId:
            raise TypeError("PinnedDefinitionReference definition_id must be a DefinitionId")
        if type(self.definition_revision) is not int:
            raise TypeError("PinnedDefinitionReference revision must be an exact integer")
        if self.definition_revision < 1:
            raise ValueError("PinnedDefinitionReference revision must be a positive exact integer")
        if type(self.kind) is not str:
            raise TypeError("PinnedDefinitionReference kind must be a string")
        if self.kind != "pinned_definition":
            raise ValueError("PinnedDefinitionReference kind must be 'pinned_definition'")


type CompanyDefinitionReference = DefinitionId | PinnedDefinitionReference
type DefinitionReference = CompanyDefinitionReference | ReferenceDefinitionId


@dataclass(frozen=True, kw_only=True, init=False)
class Page[T]:
    """Immutable page of results and an optional opaque continuation cursor."""

    items: tuple[T, ...]
    next_cursor: PageCursor | None

    def __init__(self, *, items: Sequence[T], next_cursor: PageCursor | None = None) -> None:
        """Snapshot input items and validate the optional cursor."""
        if not is_non_string_sequence(items):
            raise TypeError("Page items must be a sequence such as a list or tuple")
        if next_cursor is not None and type(next_cursor) is not PageCursor:
            raise TypeError("Page next_cursor must be a PageCursor or None")
        object.__setattr__(self, "items", tuple(items))
        object.__setattr__(self, "next_cursor", next_cursor)
