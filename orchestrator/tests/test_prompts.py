"""llm/prompts.py's money pre-conversion — MCP_ENGINES.md §Pipeline stages."""

from decimal import Decimal

from app.llm.prompts import format_inr, money_annotations


def test_format_inr_picks_crore_lakh_or_plain_rupees() -> None:
    assert format_inr(28_608_029_608.93) == "₹2,860.80 crore"
    assert format_inr(4_50_000) == "₹4.50 lakh"
    assert format_inr(999) == "₹999.00"


def test_money_annotations_only_covers_money_looking_columns() -> None:
    # shop_count is a plain count, not a rupee figure — annotating it as lakh/crore
    # would be wrong on its face, so only total_revenue gets a conversion line.
    text = money_annotations(
        ["shop_count", "total_revenue"], [{"shop_count": 9362, "total_revenue": 28_608_029_608.93}]
    )
    assert "shop_count" not in text
    assert "total_revenue = ₹2,860.80 crore" in text


def test_money_annotations_is_empty_with_no_money_columns() -> None:
    assert money_annotations(["shop_count"], [{"shop_count": 9362}]) == ""


def test_money_annotations_covers_a_decimal_value() -> None:
    # asyncpg returns a Postgres NUMERIC (every SUM/AVG over a money column) as
    # decimal.Decimal, not float — confirmed live against a real beer-revenue
    # question, a plain `int | float` check silently skipped the annotation for
    # every real aggregate, leaving the model to redo the lakh/crore conversion
    # itself and get it wrong by a factor of ten.
    text = money_annotations(
        ["total_beer_revenue"], [{"total_beer_revenue": Decimal("71428717508.8")}]
    )
    assert "total_beer_revenue = ₹7,142.87 crore" in text
