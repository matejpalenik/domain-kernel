"""Supply scripted whole-question discovery responses."""

from __future__ import annotations

import json
from typing import final, override

from domain_kernel import (
    ModelGateway,
    ModelRequest,
    ModelResponse,
)
from tests.support.discovery.create_discovery_workspace import DISCOVERY_STATEMENT


@final
class V23Gateway(ModelGateway):
    """Record requests and return a draft or repair with pinned evidence."""

    supports_schema_discovery = True

    def __init__(self, *, malformed: bool = False) -> None:
        """Configure whether to return a deliberately malformed draft."""
        self.malformed = malformed
        self.requests: list[ModelRequest] = []

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.malformed:
            return ModelResponse(output_json='{"concepts":', model_id="test/v23")
        if request.provider_stage == "schema-compact-draft":
            body: dict[str, object] = {
                "concepts": [
                    {
                        "name": "application-code",
                        "display_name": "Application code",
                        "meaning": "A lookup code for a provision.",
                        "question_ids": ["purpose"],
                        "witnesses": ["E1.1"],
                        "modality": "descriptive",
                        "qualifiers": [],
                        "applicability": "This application.",
                    }
                ],
                "relationships": [],
                "questions": [],
                "unresolved_facets": [],
            }
        else:
            assert request.provider_stage == "schema-compact-repair"
            body = {
                "upsert": {"concepts": [], "relationships": [], "questions": []},
                "drop": [],
                "label_edits": [],
                "label_flags": [],
                "checks": [
                    {
                        "facet_id": 1,
                        "example": DISCOVERY_STATEMENT,
                        "contrast": None,
                        "status": "supported",
                        "concepts": ["application-code"],
                        "links": [],
                        "witnesses": ["E1.1"],
                        "reason": "The source explicitly describes a lookup code.",
                    }
                ],
            }
        return ModelResponse(output_json=json.dumps(body), model_id="test/v23")
