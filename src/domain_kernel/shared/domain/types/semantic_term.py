"""Type contract for semantic term."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.model_term_reference import ModelTermReference
from domain_kernel.shared.domain.value_objects.ontology_term_reference import OntologyTermReference

type SemanticTerm = ModelTermReference | OntologyTermReference
