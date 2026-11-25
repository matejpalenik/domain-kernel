"""Validate and tag exact native scalar values in descriptive decisions."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType

from domain_kernel.shared.domain.model_values import DataType, ScalarDataType
from domain_kernel.shared.domain.types.decision_scalar import DecisionScalar

DECISION_SCALAR_TYPES: Mapping[type[object], ScalarDataType] = MappingProxyType(
    {
        str: DataType.STRING,
        bool: DataType.BOOLEAN,
        int: DataType.INTEGER,
        Decimal: DataType.DECIMAL,
        date: DataType.DATE,
        datetime: DataType.DATETIME,
    }
)


@dataclass(frozen=True, kw_only=True)
class DecisionValue:
    """One exact native scalar literal."""

    value: DecisionScalar

    def __post_init__(self) -> None:
        """Validate native type and represent an instant in its canonical time zone."""
        if type(self.value) not in DECISION_SCALAR_TYPES:
            raise TypeError("Use an exact string, bool, integer, Decimal, date or datetime")
        if type(self.value) is Decimal and not self.value.is_finite():
            raise ValueError("Decision decimals must be finite")
        if type(self.value) is datetime:
            if self.value.utcoffset() is None:
                raise ValueError("Decision times require a time zone")
            object.__setattr__(self, "value", self.value.astimezone(UTC))

    @property
    def data_type(self) -> ScalarDataType:
        """Derive the exact scalar tag without treating bool as int or datetime as date."""
        return DECISION_SCALAR_TYPES[type(self.value)]
