"""Optional RapidFuzz implementation of lexical candidate scoring."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, final, override, runtime_checkable

from domain_kernel.reconciliation.application.ports import SimilarityScorer
from domain_kernel.shared.errors import MissingCapabilityError
from domain_kernel.shared.validation import require_text


@runtime_checkable
class _Ratio(Protocol):
    def ratio(self, s1: str, s2: str) -> float: ...


@final
class RapidFuzzSimilarityScorer(SimilarityScorer):
    """Scale RapidFuzz's normalized Indel similarity to the SDK score range."""

    def __init__(self) -> None:
        """Load the optional adapter when explicitly selected."""
        try:
            fuzz = import_module(name="rapidfuzz.fuzz")
        except ImportError:
            raise MissingCapabilityError(
                message="Install the Domain Kernel matching extra."
            ) from None
        if not isinstance(fuzz, _Ratio):
            raise MissingCapabilityError(message="Install a compatible RapidFuzz package.")
        self._fuzz = fuzz

    @override
    def score(self, *, left: str, right: str) -> float:
        """Return lexical similarity with no semantic judgment."""
        require_text(value=left, field="Left label")
        require_text(value=right, field="Right label")
        return self._fuzz.ratio(left, right) / 100
