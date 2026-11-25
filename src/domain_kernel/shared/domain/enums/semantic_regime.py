"""The semantics under which a result is claimed."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class SemanticRegime(StrEnum):
    """The semantics under which a result is claimed."""

    RDFS = "rdfs"
    OWL_DIRECT = "owl_direct"
    OWL_RDF = "owl_rdf"
