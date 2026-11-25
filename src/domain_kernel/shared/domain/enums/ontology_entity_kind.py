"""Declared role of a term in a pinned document graph."""

from enum import StrEnum, unique


@unique
class OntologyEntityKind(StrEnum):
    """Declared role of a term in a pinned document graph."""

    CLASS = "class"
    OBJECT_PROPERTY = "object_property"
    DATA_PROPERTY = "data_property"
    ANNOTATION_PROPERTY = "annotation_property"
    RDF_PROPERTY = "rdf_property"
    DATATYPE = "datatype"
    INDIVIDUAL = "individual"
    SKOS_CONCEPT = "skos_concept"
