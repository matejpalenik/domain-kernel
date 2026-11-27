"""Type contract for lifecycle operation."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.plans.restore_definition import RestoreDefinition
from domain_kernel.shared.domain.value_objects.plans.retire_definition import RetireDefinition
from domain_kernel.shared.domain.value_objects.plans.revise_definition import ReviseDefinition

type LifecycleOperation = ReviseDefinition | RetireDefinition | RestoreDefinition
