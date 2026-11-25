"""Type contract for lifecycle operation."""

from __future__ import annotations

from domain_kernel.shared.domain.operations.restore_definition import RestoreDefinition
from domain_kernel.shared.domain.operations.retire_definition import RetireDefinition
from domain_kernel.shared.domain.operations.revise_definition import ReviseDefinition

type LifecycleOperation = ReviseDefinition | RetireDefinition | RestoreDefinition
