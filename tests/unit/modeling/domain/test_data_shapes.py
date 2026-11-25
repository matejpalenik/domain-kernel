from __future__ import annotations

import pytest

from domain_kernel.modeling.domain.identifiers.attribute_id import AttributeId
from domain_kernel.modeling.domain.identifiers.definition_id import DefinitionId
from domain_kernel.shared.contracts import Count
from domain_kernel.shared.domain.entities.attribute_definition import AttributeDefinition
from domain_kernel.shared.domain.entities.key_definition import KeyDefinition
from domain_kernel.shared.domain.enums.collection_kind import CollectionKind
from domain_kernel.shared.domain.enums.constraint_language import ConstraintLanguage
from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.enums.nullability import Nullability
from domain_kernel.shared.domain.value_objects.constraint_definition import ConstraintDefinition
from domain_kernel.shared.domain.value_objects.decimal_facets import DecimalFacets
from domain_kernel.shared.domain.value_objects.decimal_scale import DecimalScale
from domain_kernel.shared.domain.value_objects.scalar_value_type import ScalarValueType
from domain_kernel.shared.domain.value_objects.terminology import Terminology
from domain_kernel.shared.domain.value_objects.value_set_type import ValueSetType


def test_factories_resolve_names_and_preserve_typed_inputs() -> None:
    vocabulary = DefinitionId(value="vocabulary")
    first = AttributeDefinition.value_set(
        value_set=vocabulary,
        display_name=" Actor_Role! ",
        required=True,
        collection=CollectionKind.SET,
        max_items=Count(value=2),
    )
    second = AttributeDefinition(
        value_type=ValueSetType(value_set=vocabulary),
        name="actor-role",
        required=True,
        collection=CollectionKind.SET,
        max_items=Count(value=2),
    )

    assert first.id != second.id
    assert first.name == second.name == "actor-role"
    assert first.display_name == " Actor_Role! "
    assert second.display_name == "actor-role"
    assert first.value_type == second.value_type == ValueSetType(value_set=vocabulary)
    assert first.min_items == second.min_items == Count(value=0)
    assert first.max_items == second.max_items == Count(value=2)


def test_presence_is_independent_of_collection_size_and_nullability() -> None:
    required = AttributeDefinition.string(
        name="required-codes", required=True, collection=CollectionKind.SET
    )
    optional = AttributeDefinition.string(
        name="optional-codes", collection=CollectionKind.LIST, min_items=Count(value=1)
    )
    nullable = AttributeDefinition.string(
        name="optional-evidence", required=True, nullability=Nullability.ALLOWED
    )

    assert (required.required, required.min_items, required.max_items) == (
        True,
        Count(value=0),
        None,
    )
    assert (optional.required, optional.min_items, optional.max_items) == (
        False,
        Count(value=1),
        None,
    )
    assert (nullable.required, nullable.min_items, nullable.max_items) == (True, None, None)
    assert nullable.nullability is Nullability.ALLOWED


def test_attribute_rejects_incompatible_collection_options() -> None:
    with pytest.raises(ValueError, match="SINGLE"):
        _ = AttributeDefinition.string(name="code", max_items=Count(value=1))
    with pytest.raises(ValueError, match="null"):
        _ = AttributeDefinition.string(
            name="codes", collection=CollectionKind.SET, nullability=Nullability.ALLOWED
        )
    with pytest.raises(ValueError, match="maximum"):
        _ = AttributeDefinition.string(
            name="codes",
            collection=CollectionKind.LIST,
            min_items=Count(value=2),
            max_items=Count(value=1),
        )


def test_shape_choices_require_declared_types() -> None:
    with pytest.raises(TypeError, match="Collection"):
        _ = AttributeDefinition.string(name="role", collection="set")  # pyright: ignore[reportArgumentType] -- runtime caller
    with pytest.raises(TypeError, match="Required"):
        _ = AttributeDefinition.string(name="role", required=1)  # pyright: ignore[reportArgumentType] -- runtime caller
    with pytest.raises(TypeError, match="reference"):
        _ = AttributeDefinition.value_set(value_set="roles", name="role")  # pyright: ignore[reportArgumentType] -- runtime caller
    with pytest.raises(ValueError, match="DECIMAL"):
        _ = ScalarValueType(
            data_type=DataType.STRING, decimal=DecimalFacets(scale=DecimalScale(value=2))
        )


def test_attribute_and_key_detach_inputs() -> None:
    constraint = ConstraintDefinition(
        id="notes",
        description="Explain the code",
        language=ConstraintLanguage.TEXT,
        expression="Use a local code.",
    )
    constraints = [constraint]
    attribute = AttributeDefinition.string(name="record-code", constraints=constraints)
    fields = [attribute.id]
    key = KeyDefinition(display_name="Record identity", attributes=fields)
    constraints.clear()
    fields.clear()

    assert attribute.constraints == (constraint,)
    assert attribute.terminology == Terminology()
    assert key.attributes == (attribute.id,)
    assert key.name == "record-identity"


def test_keys_reject_empty_or_repeated_attribute_ids() -> None:
    field = AttributeId(value="field")
    with pytest.raises(ValueError, match="at least one"):
        _ = KeyDefinition(name="empty-key", attributes=[])
    with pytest.raises(ValueError, match="distinct"):
        _ = KeyDefinition(name="repeated-key", attributes=[field, field])


def test_name_override_must_be_explicit_when_display_cannot_derive_a_lookup() -> None:
    with pytest.raises(ValueError, match="explicit name"):
        _ = AttributeDefinition.string(display_name="Déployeur")
    with pytest.raises(ValueError, match="lookup name"):
        _ = AttributeDefinition.string(display_name="Provider", name="Provider")
    attribute = AttributeDefinition.string(display_name="Déployeur", name="deployer")
    assert attribute.name == "deployer"
    assert attribute.display_name == "Déployeur"
