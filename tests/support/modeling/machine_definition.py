"""Build the machine definition used by review and record encoding tests."""

from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.contracts import ModelScope
from domain_kernel.shared.domain.definitions import ConceptDefinition, Definition


def make_machine_definition() -> Definition:
    """Create the first revision of the machine definition in a test model."""
    scope = ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model"))
    return Definition(
        id=DefinitionId(value="machine"),
        scope=scope,
        revision=1,
        name="machine",
        display_name="Machine",
        meaning="Physical production asset.",
        body=ConceptDefinition(),
    )
