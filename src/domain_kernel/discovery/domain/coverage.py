"""Discovery windows tied to immutable, independently reopenable source evidence."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation
from domain_kernel.shared.validators.sequence_validation import SequenceValidation
from domain_kernel.shared.validators.text_validation import TextValidation
from domain_kernel.sources.domain.models import Evidence, SourceRevision


@dataclass(frozen=True, kw_only=True)
class DiscoveryWindow:
    """Half-open Unicode offsets within the original evidence excerpt."""

    evidence: Evidence
    start: int
    end: int
    completed: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        """Keep a nonempty source span and its coverage disposition together."""
        RuntimeTypeValidation.require_exact(
            value=self.evidence, expected=Evidence, field="Discovery window evidence"
        )
        RuntimeTypeValidation.require_exact(
            value=self.start, expected=int, field="Discovery window start"
        )
        RuntimeTypeValidation.require_exact(
            value=self.end, expected=int, field="Discovery window end"
        )
        RuntimeTypeValidation.require_exact(
            value=self.completed, expected=bool, field="Discovery window disposition"
        )
        if not 0 <= self.start < self.end or self.completed != (self.reason is None):
            raise ValueError("Use a nonempty source span and explain any deferred work.")
        if self.reason is not None:
            TextValidation.require_text(value=self.reason, field="Deferred reason")


@dataclass(frozen=True, kw_only=True)
class DiscoveryCoverage:
    """Completed and outstanding omission windows for one exact source revision."""

    source: SourceRevision
    windows: tuple[DiscoveryWindow, ...]

    def __post_init__(self) -> None:
        """Reject source substitutions and overlapping windows."""
        RuntimeTypeValidation.require_exact(
            value=self.source, expected=SourceRevision, field="Coverage source"
        )
        windows = SequenceValidation.snapshot_sequence(
            items=self.windows, item_type=DiscoveryWindow, field="Coverage windows"
        )
        end_by_evidence: dict[Evidence, int] = {}
        for window in sorted(windows, key=lambda item: item.start):
            if window.evidence.source != self.source or window.start < end_by_evidence.get(
                window.evidence, 0
            ):
                raise ValueError("Use disjoint windows from the exact coverage source.")
            end_by_evidence[window.evidence] = window.end
        object.__setattr__(self, "windows", windows)

    @property
    def completed(self) -> tuple[DiscoveryWindow, ...]:
        """Return the windows with complete responses."""
        return tuple(window for window in self.windows if window.completed)

    @property
    def deferred(self) -> tuple[DiscoveryWindow, ...]:
        """Return the original spans eligible for continuation."""
        return tuple(window for window in self.windows if not window.completed)

    @property
    def has_deferred(self) -> bool:
        """Return whether any omission work remains."""
        return bool(self.deferred)
