from decimal import Decimal

import pytest

from etl.normalize import (
    NormalizationError,
    normalize_money,
    normalize_volume_bl,
    parse_financial_year,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2014-15", 2014), ("FY2014-15", 2014), ("2014_15", 2014), ("2014", 2014)],
)
def test_parse_financial_year_accepts_known_formats(raw: str, expected: int) -> None:
    assert parse_financial_year(raw) == expected


def test_parse_financial_year_rejects_garbage() -> None:
    with pytest.raises(NormalizationError):
        parse_financial_year("not a year")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("₹1,23,456.00", Decimal("123456.00")), ("1000", Decimal("1000")), (" 500 ", Decimal("500"))],
)
def test_normalize_money_strips_currency_formatting(raw: str, expected: Decimal) -> None:
    assert normalize_money(raw) == expected


def test_normalize_money_rejects_non_numeric() -> None:
    with pytest.raises(NormalizationError):
        normalize_money("not a number")


def test_normalize_volume_bl_converts_kilolitres() -> None:
    assert normalize_volume_bl("2", "KL") == Decimal("2000")


def test_normalize_volume_bl_rejects_unknown_unit() -> None:
    with pytest.raises(NormalizationError):
        normalize_volume_bl("10", "gallons")
