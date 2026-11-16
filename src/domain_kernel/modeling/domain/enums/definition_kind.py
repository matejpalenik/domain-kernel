"""Stable wire discriminators for definition bodies."""

from enum import StrEnum, unique


@unique
class DefinitionKind(StrEnum):
    """Closed set of definition kinds in the SDK design."""

    CONCEPT = "concept"
    RELATIONSHIP = "relationship"
    PROCESS = "process"
    BUSINESS_DECISION = "business_decision"
    RULE = "rule"
    SEMANTIC_LINK = "semantic_link"
    ONTOLOGY_MODULE = "ontology_module"
    VALUE_SET = "value_set"
    UNIT = "unit"
    STRUCTURED_VALUE = "structured_value"
    ACCEPTANCE_CHECK = "acceptance_check"
