"""Supported asserted predicates using their standard IRIs."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class SemanticRelation(StrEnum):
    """Supported asserted predicates using their standard IRIs."""

    SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
    SUBPROPERTY_OF = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf"
    EQUIVALENT_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"
    EQUIVALENT_PROPERTY = "http://www.w3.org/2002/07/owl#equivalentProperty"
    DISJOINT_WITH = "http://www.w3.org/2002/07/owl#disjointWith"
    INVERSE_OF = "http://www.w3.org/2002/07/owl#inverseOf"
    SAME_AS = "http://www.w3.org/2002/07/owl#sameAs"
    DIFFERENT_FROM = "http://www.w3.org/2002/07/owl#differentFrom"
    EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"
    CLOSE_MATCH = "http://www.w3.org/2004/02/skos/core#closeMatch"
    BROAD_MATCH = "http://www.w3.org/2004/02/skos/core#broadMatch"
    NARROW_MATCH = "http://www.w3.org/2004/02/skos/core#narrowMatch"
    RELATED_MATCH = "http://www.w3.org/2004/02/skos/core#relatedMatch"
    SEE_ALSO = "http://www.w3.org/2000/01/rdf-schema#seeAlso"
    IS_DEFINED_BY = "http://www.w3.org/2000/01/rdf-schema#isDefinedBy"
