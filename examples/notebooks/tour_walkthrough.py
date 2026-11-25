"""Small selection and display helpers for the full-document walkthrough."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from domain_kernel import ConceptDefinition, DocumentSpan, RelationshipDefinition, ScalarValueType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain_kernel import DefinitionReference, DomainModelBundle, Evidence, Model, ReviewCase


async def select_concept(  # noqa: PLR0913 -- The sample review pins name, meaning, and evidence.
    *,
    model: Model,
    cases: Sequence[ReviewCase],
    name: str,
    title: str,
    meaning: str,
    evidence: Sequence[Evidence],
    actor: str,
) -> ReviewCase:
    """Use a supported draft or author a missing concept from the inspected pages."""
    for case in cases:
        if (
            len(case.definitions) == 1
            and case.definitions[0].name == name
            and isinstance(case.definitions[0].body, ConceptDefinition)
            and case.evidence
            and set(case.evidence).issubset(evidence)
        ):
            return case
    _ = sys.stdout.write(f"Authoring {name} from the PDF using the sample review's evidence.\n")
    return await model.propose_definition(
        actor=actor,
        name=name,
        display_name=title,
        meaning=meaning,
        body=ConceptDefinition(),
        evidence=evidence,
        reason="Author the missing meaning from the inspected PDF pages.",
        idempotency_key=f"author-{name}",
    )


def show_model(*, bundle: DomainModelBundle) -> None:
    """Show every live definition, its shape or endpoints, and its PDF citations."""
    definitions = bundle.content.definitions
    names: dict[DefinitionReference, str] = {item.id: item.display_name for item in definitions}
    lines = [
        f"Complete published model · {bundle.version} · {len(definitions)} definitions",
    ]
    for definition in definitions:
        body = definition.body
        lines.extend(
            (
                "",
                f"{body.kind.value.title()} · {definition.display_name} ({definition.name})",
                definition.meaning,
            )
        )
        if isinstance(body, ConceptDefinition):
            for field in body.attributes:
                value_type = field.value_type
                shape = (
                    value_type.data_type.value
                    if isinstance(value_type, ScalarValueType)
                    else value_type.kind
                )
                presence = "required" if field.required else "optional"
                lines.append(f"  Field {field.name} · {shape} · {presence}")
        if isinstance(body, RelationshipDefinition):
            source = names.get(body.source_concept_id, str(body.source_concept_id))
            target = names.get(body.target_concept_id, str(body.target_concept_id))
            lines.append(f"  {source} → {target}")
        pages = sorted(
            item.locator.page
            for item in definition.evidence
            if isinstance(item.locator, DocumentSpan) and item.locator.page is not None
        )
        lines.append(f"  AI Act PDF pages {', '.join(map(str, pages))}")
    _ = sys.stdout.write("\n".join(lines) + "\n")
