"""Check exact scalar representations used by the complete bundle codec."""

from binascii import Error
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from domain_kernel.modeling.domain.bundle_shapes import wire_shape
from domain_kernel.modeling.domain.errors.wire_shape_error import WireShapeError


def test_bundle_scalar_codecs_use_exact_canonical_lexical_values() -> None:
    decimal = wire_shape(hint=Decimal)
    assert decimal.render(Decimal("120.300")) == "120.3"
    assert decimal.render(Decimal("-0.000")) == "0"
    assert decimal.parse("120.3") == Decimal("120.3")
    with pytest.raises(WireShapeError):
        _ = decimal.parse("120.30")

    day = wire_shape(hint=date)
    assert day.render(date(2024, 7, 12)) == "2024-07-12"
    instant = wire_shape(hint=datetime)
    local = datetime(2024, 7, 12, 12, tzinfo=timezone(timedelta(hours=2)))
    assert instant.render(local) == "2024-07-12T10:00:00.000000Z"
    assert instant.parse("2024-07-12T10:00:00.000000Z") == datetime(2024, 7, 12, 10, tzinfo=UTC)
    with pytest.raises(WireShapeError):
        _ = instant.parse("2024-07-12T12:00:00.000000+02:00")


def test_bundle_binary_scalar_requires_exact_standard_padded_base64() -> None:
    binary = wire_shape(hint=bytes)
    assert binary.render(b"\xfb") == "+w=="
    assert binary.parse("+w==") == b"\xfb"
    with pytest.raises(Error):
        _ = binary.parse("-w==")
    with pytest.raises(Error):
        _ = binary.parse("+w")
    with pytest.raises(WireShapeError):
        _ = binary.parse("+/==")
