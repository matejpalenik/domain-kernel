"""Type contract for scalar data type."""

from __future__ import annotations

from typing import Literal

from domain_kernel.shared.domain.enums.data_type import DataType

type ScalarDataType = Literal[
    DataType.STRING,
    DataType.INTEGER,
    DataType.DECIMAL,
    DataType.BOOLEAN,
    DataType.DATE,
    DataType.DATETIME,
]
