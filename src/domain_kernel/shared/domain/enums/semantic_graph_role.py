"""The graph addressed by a semantic document."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class SemanticGraphRole(StrEnum):
    """The graph addressed by a semantic document."""

    ONTOLOGY = "ontology"
    MODEL_METADATA = "model_metadata"
    MODEL_SHAPES = "model_shapes"
    INSTANCE_SHAPES = "instance_shapes"
