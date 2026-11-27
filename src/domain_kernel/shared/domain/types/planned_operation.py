"""Type contract for planned operation."""

from __future__ import annotations

from domain_kernel.shared.domain.types.lifecycle_operation import LifecycleOperation
from domain_kernel.shared.domain.value_objects.plans.correct_mapping import CorrectMapping
from domain_kernel.shared.domain.value_objects.plans.create_definition import CreateDefinition
from domain_kernel.shared.domain.value_objects.plans.include_case import IncludeCase

type PlannedOperation = CreateDefinition | LifecycleOperation | IncludeCase | CorrectMapping
