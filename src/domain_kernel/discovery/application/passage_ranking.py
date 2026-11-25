"""Rank exact source spans for verification within a caller-selected evidence boundary."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_WORD = re.compile(r"[^\W_]+")
# Keep negation and modal verbs. They can change the direction of a verification decision.
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    ]
)


def _terms(text: str) -> Counter[str]:
    return Counter(
        word for match in _WORD.finditer(text.casefold()) if (word := match[0]) not in _STOP
    )


def rank_passages(*, query: str, passages: Sequence[str], limit: int) -> tuple[int, ...]:
    """BM25 over distinct supplied spans, returning original positions and omitting zero scores."""
    if limit < 1:
        raise ValueError("Use a positive evidence limit.")
    requested = set(_terms(query))
    if not requested:
        return ()
    unique: dict[str, int] = {}
    for index, passage in enumerate(passages):
        if passage.strip():
            _ = unique.setdefault(passage, index)
    indexed = {i: _terms(passage) for passage, i in unique.items()}
    if not indexed:
        return ()
    size = len(indexed)
    mean_length = sum(words.total() for words in indexed.values()) / size or 1.0
    frequency = Counter(
        word for words in indexed.values() for word in requested.intersection(words)
    )
    weights = {
        word: math.log1p((size - count + 0.5) / (count + 0.5)) for word, count in frequency.items()
    }
    scores: dict[int, float] = {}
    for index, words in indexed.items():
        penalty = 1.2 * (0.25 + 0.75 * words.total() / mean_length)
        score = sum(
            weights[word] * words[word] * 2.2 / (words[word] + penalty)
            for word in words
            if word in weights
        )
        if score > 0:
            scores[index] = score
    return tuple(sorted(scores, key=lambda i: (-scores[i], i))[:limit])
