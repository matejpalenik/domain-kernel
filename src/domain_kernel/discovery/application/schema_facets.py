"""An issued competency question or grounded gap."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Facet:
    """A question with its original passage leads."""

    id: int
    question_id: str
    text: str
    queries: tuple[str, ...]
    leads: tuple[int, ...]
