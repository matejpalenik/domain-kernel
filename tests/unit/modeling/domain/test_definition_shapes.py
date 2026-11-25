from __future__ import annotations

import pytest

from domain_kernel._shared.domain.data_shapes import (
    AttributeDefinition,
    KeyDefinition,
    QuantityBinding,
    StructuredValueType,
)
from domain_kernel._shared.domain.definitions import (
    Concept,
    ConceptDefinition,
    StructuredValueDefinition,
    UnitDefinition,
    ValueSetDefinition,
    ValueSetMember,
)
from domain_kernel._shared.domain.model_values import (
    BusinessCode,
    CollectionKind,
    LabelText,
    MeaningText,
    ValueSetMembership,
)
from domain_kernel._shared.domain.ontology_assets import (
    Iri,
    OntologyDocumentPin,
    OntologyEntityKind,
    OntologyTermReference,
)
from domain_kernel.modeling.domain.errors.attribute_already_exists_error import (
    AttributeAlreadyExistsError,
)
from domain_kernel.modeling.domain.errors.attribute_not_found_error import AttributeNotFoundError
from domain_kernel.modeling.domain.errors.key_already_exists_error import KeyAlreadyExistsError
from domain_kernel.modeling.domain.errors.key_not_found_error import KeyNotFoundError
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.modeling.domain.identifiers.model_id import ModelId
from domain_kernel.projects.domain.identifiers.project_id import ProjectId
from domain_kernel.shared.contracts import ModelScope
from domain_kernel.shared.identifiers.content_hash import ContentHash


def _concept(*, body: ConceptDefinition) -> Concept:
    return Concept(
        id=DefinitionId(value="provision"),
        scope=ModelScope(project_id=ProjectId(value="project"), model_id=ModelId(value="model")),
        revision=2,
        name="legal-provision",
        display_name="Legal provision",
        meaning="A provision in the selected edition.",
        body=body,
    )


def test_concept_returns_exact_inspected_attributes_and_keys() -> None:
    section = AttributeDefinition.string(display_name="Section", required=True)
    code = AttributeDefinition.string(display_name="Record code", required=True)
    key = KeyDefinition(display_name="Identity", attributes=[section.id, code.id])
    fields = [section, code]
    keys = [key]
    concept = _concept(body=ConceptDefinition(attributes=fields, keys=keys))
    fields.clear()
    keys.clear()

    assert concept.attributes == (section, code)
    assert concept.keys == (key,)
    assert concept.get_attribute(name="record-code") is code
    assert concept.get_attribute(attribute_id=section.id) is section
    assert concept.get_key(name="identity") is concept.get_key(key_id=key.id) is key
    with pytest.raises(AttributeNotFoundError, match="exact attribute"):
        _ = concept.get_attribute(name="Record code")
    with pytest.raises(KeyNotFoundError, match="exact key"):
        _ = concept.get_key(name="unknown")
    with pytest.raises(ValueError, match="exactly one"):
        _ = concept.get_attribute(name="section", attribute_id=section.id)
    with pytest.raises(ValueError, match="exactly one"):
        _ = concept.get_key()


def test_concept_rejects_duplicate_child_names_in_their_owner() -> None:
    field = AttributeDefinition.string(name="record-code", required=True)
    with pytest.raises(AttributeAlreadyExistsError):
        _ = ConceptDefinition(
            attributes=[field, AttributeDefinition.string(display_name="Record code")],
        )
    with pytest.raises(KeyAlreadyExistsError):
        _ = ConceptDefinition(
            attributes=[field],
            keys=[
                KeyDefinition(name="record-code", attributes=[field.id]),
                KeyDefinition(name="record-code", attributes=[field.id]),
            ],
        )
    assert ConceptDefinition(
        attributes=[field], keys=[KeyDefinition(name="record-code", attributes=[field.id])]
    ).attributes == (field,)


def test_keys_require_existing_required_single_non_null_leaves() -> None:
    optional = AttributeDefinition.string(name="optional")
    collection = AttributeDefinition.string(
        name="many", required=True, collection=CollectionKind.SET
    )
    nested = AttributeDefinition(
        name="embedded",
        required=True,
        value_type=StructuredValueType(structure=DefinitionId(value="locator")),
    )
    for field in (optional, collection, nested):
        key = KeyDefinition(name="identity", attributes=[field.id])
        with pytest.raises(ValueError, match="required, single-valued and non-null"):
            _ = ConceptDefinition(attributes=[field], keys=[key])
        with pytest.raises(ValueError, match="owning concept"):
            _ = ConceptDefinition(keys=[key])


def _term(*, entity_kind: OntologyEntityKind) -> OntologyTermReference:
    return OntologyTermReference(
        source=OntologyDocumentPin(
            document_iri=Iri(value="urn:example:units"),
            content_hash=ContentHash(value="sha256:" + "0" * 64),
        ),
        term_iri=Iri(value="urn:example:units:hour"),
        entity_kind=entity_kind,
    )


def test_vocabularies_preserve_codes_and_require_a_single_unit_binding() -> None:
    unit = DefinitionId(value="hour")
    term = _term(entity_kind=OntologyEntityKind.INDIVIDUAL)
    hour = ValueSetMember(
        code=BusinessCode(value="h"),
        label=LabelText(value="Hour"),
        meaning=MeaningText(value="An hour of processing time"),
        unit=unit,
    )
    supplied = [hour]
    vocabulary = ValueSetDefinition(membership=ValueSetMembership.CLOSED, members=supplied)
    supplied.clear()
    assert vocabulary.members == (hour,)
    with pytest.raises(ValueError, match="distinct"):
        _ = ValueSetDefinition(membership=ValueSetMembership.OPEN, members=[hour, hour])
    with pytest.raises(ValueError, match="unit or ontology term"):
        _ = ValueSetMember(
            code=hour.code, label=hour.label, meaning=hour.meaning, unit=unit, ontology_term=term
        )
    with pytest.raises(ValueError, match="individuals"):
        _ = UnitDefinition(ontology_term=_term(entity_kind=OntologyEntityKind.CLASS))


def test_quantity_requires_a_matching_decimal_magnitude_and_code_field() -> None:
    magnitude = AttributeDefinition.decimal(name="magnitude", required=True)
    units = AttributeDefinition.value_set(
        name="unit", required=True, value_set=DefinitionId(value="duration-units")
    )
    quantity = QuantityBinding(magnitude=magnitude.id, unit=units.id)
    structure = StructuredValueDefinition(attributes=[magnitude, units], quantity=quantity)
    assert structure.quantity is not None
    assert structure.quantity == quantity
    assert structure.quantity.quantity_kind is None
    text = AttributeDefinition.string(name="wrong-magnitude", required=True)
    with pytest.raises(ValueError, match="decimal"):
        _ = StructuredValueDefinition(
            attributes=[text, units],
            quantity=QuantityBinding(magnitude=text.id, unit=units.id),
        )
    with pytest.raises(ValueError, match="fields on this structured value"):
        _ = StructuredValueDefinition(attributes=[magnitude], quantity=quantity)
