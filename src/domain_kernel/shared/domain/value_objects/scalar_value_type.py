"""Type of an exact scalar business value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain_kernel.shared.domain.enums.data_type import DataType
from domain_kernel.shared.domain.validators.shape_field_validation import ShapeFieldValidation
from domain_kernel.shared.domain.value_objects.decimal_facets import DecimalFacets
from domain_kernel.shared.validators.runtime_type_validation import RuntimeTypeValidation

if TYPE_CHECKING:
    from domain_kernel.shared.domain.types.scalar_data_type import ScalarDataType


_SCALAR_TYPES = frozenset(
    {
        DataType.STRING,
        DataType.INTEGER,
        DataType.DECIMAL,
        DataType.BOOLEAN,
        DataType.DATE,
        DataType.DATETIME,
    }
)


@dataclass(frozen=True, kw_only=True)
class ScalarValueType:
    """Type of an exact scalar business value."""

    data_type: ScalarDataType
    decimal: DecimalFacets | None = None
    kind: Literal["scalar"] = "scalar"

    def __post_init__(self) -> None:
        """Limit facets to exact decimal types and require the fixed tag."""
        ShapeFieldValidation.require_attribute_type_kind(kind=self.kind, expected="scalar")

        RuntimeTypeValidation.require_exact(
            value=self.data_type, expected=DataType, field="Scalar data type"
        )
        if self.data_type not in _SCALAR_TYPES:
            raise ValueError("Choose a scalar data type for ScalarValueType")

        if self.decimal is not None:
            RuntimeTypeValidation.require_exact(
                value=self.decimal, expected=DecimalFacets, field="Scalar facets"
            )
            if self.data_type is not DataType.DECIMAL:
                raise ValueError("Decimal facets require the DECIMAL data type")
