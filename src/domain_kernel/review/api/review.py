"""Public confirmation construction against a captured source handle."""

from __future__ import annotations

from dataclasses import dataclass

from domain_kernel.review.domain.decisions import ConfirmStatement as _ConfirmStatement
from domain_kernel.review.domain.errors.invalid_decision_error import InvalidDecisionError
from domain_kernel.sources.domain.models import IngestedSource


@dataclass(frozen=True, kw_only=True)
class ConfirmStatement(_ConfirmStatement):
    """An explicit confirmation over a separately captured source."""

    @classmethod
    def from_statement(
        cls, *, source: IngestedSource, authority: str, reason: str
    ) -> ConfirmStatement:
        """Prepare a recorded decision from the exact source revision and citations."""
        if type(source) is not IngestedSource:
            raise InvalidDecisionError(
                message="Select the captured statement returned by ingestion."
            )
        return cls._from_statement(
            revision=source.revision,
            evidence=source.evidence,
            authority=authority,
            reason=reason,
        )
