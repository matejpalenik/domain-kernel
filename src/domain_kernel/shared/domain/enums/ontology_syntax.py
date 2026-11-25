"""Explicit serialization and OWL structural syntaxes."""

from enum import StrEnum, unique


@unique
class OntologySyntax(StrEnum):
    """Explicit serialization and OWL structural syntaxes."""

    TURTLE = "turtle"
    RDFXML = "rdfxml"
    JSONLD = "jsonld"
    NTRIPLES = "ntriples"
    TRIG = "trig"
    NQUADS = "nquads"
    OWLXML = "owlxml"
    FUNCTIONAL = "functional"
    MANCHESTER = "manchester"
