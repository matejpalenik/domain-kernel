"""Type contract for acceptance predicate."""

from __future__ import annotations

from domain_kernel.shared.domain.value_objects.distinct_definitions_check import (
    DistinctDefinitionsCheck,
)
from domain_kernel.shared.domain.value_objects.manual_criterion import ManualCriterion
from domain_kernel.shared.domain.value_objects.quantity_required_check import QuantityRequiredCheck

type AcceptancePredicate = DistinctDefinitionsCheck | QuantityRequiredCheck | ManualCriterion
