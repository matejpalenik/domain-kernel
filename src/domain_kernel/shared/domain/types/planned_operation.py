"""Type contract for planned operation."""

from __future__ import annotations

from domain_kernel.shared.domain.operations.correct_mapping import CorrectMapping
from domain_kernel.shared.domain.operations.create_definition import CreateDefinition
from domain_kernel.shared.domain.operations.include_case import IncludeCase
from domain_kernel.shared.domain.types.lifecycle_operation import LifecycleOperation

type PlannedOperation = CreateDefinition | LifecycleOperation | IncludeCase | CorrectMapping
