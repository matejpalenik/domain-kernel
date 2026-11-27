from __future__ import annotations

from domain_kernel.shared.domain.value_objects.candidate_pin import CandidatePin
from domain_kernel.shared.domain.value_objects.model_version import ModelVersion

type SnapshotReference = ModelVersion | CandidatePin
