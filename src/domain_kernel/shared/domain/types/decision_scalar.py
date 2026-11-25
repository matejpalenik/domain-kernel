"""Native Python values allowed in descriptive decision-table outputs."""

from datetime import date, datetime
from decimal import Decimal

type DecisionScalar = str | bool | int | Decimal | date | datetime
