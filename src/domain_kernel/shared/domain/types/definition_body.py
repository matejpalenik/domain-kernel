"""Require one exact currently implemented body record."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.acceptance_check_definition import (
    AcceptanceCheckDefinition,
)
from domain_kernel.shared.domain.value_objects.business_decision_definition import (
    BusinessDecisionDefinition,
)
from domain_kernel.shared.domain.value_objects.concept_definition import ConceptDefinition
from domain_kernel.shared.domain.value_objects.ontology_module_definition import (
    OntologyModuleDefinition,
)
from domain_kernel.shared.domain.value_objects.process_definition import ProcessDefinition
from domain_kernel.shared.domain.value_objects.relationship_definition import RelationshipDefinition
from domain_kernel.shared.domain.value_objects.rule_definition import RuleDefinition
from domain_kernel.shared.domain.value_objects.semantic_link_definition import (
    SemanticLinkDefinition,
)
from domain_kernel.shared.domain.value_objects.structured_value_definition import (
    StructuredValueDefinition,
)
from domain_kernel.shared.domain.value_objects.unit_definition import UnitDefinition
from domain_kernel.shared.domain.value_objects.value_set_definition import ValueSetDefinition

type DefinitionBody = (
    ConceptDefinition
    | StructuredValueDefinition
    | UnitDefinition
    | ValueSetDefinition
    | RelationshipDefinition
    | AcceptanceCheckDefinition
    | ProcessDefinition
    | BusinessDecisionDefinition
    | RuleDefinition
    | SemanticLinkDefinition
    | OntologyModuleDefinition
)


def require_definition_body(*, body: DefinitionBody) -> None:
    """Require one exact currently implemented body record."""
    if type(body) not in (
        ConceptDefinition,
        StructuredValueDefinition,
        UnitDefinition,
        ValueSetDefinition,
        RelationshipDefinition,
        AcceptanceCheckDefinition,
        ProcessDefinition,
        BusinessDecisionDefinition,
        RuleDefinition,
        SemanticLinkDefinition,
        OntologyModuleDefinition,
    ):
        raise TypeError("Use an implemented definition body")
