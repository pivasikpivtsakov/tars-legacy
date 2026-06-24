from collections.abc import Mapping
from decimal import Decimal

from common.money import format_money

PACKAGE_UNIT_COUNT: dict[int, int] = {
    60: 1,
    325: 5,
    660: 10,
    1800: 25,
    3850: 50,
    8100: 100,
}

PACKAGE_SIZES: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT))


def format_prices(prices: Mapping[int, Decimal] | None) -> str:
    if not prices:
        return "-"
    return ", ".join(f"{size}={format_money(prices[size])}" for size in sorted(prices, key=int))


def format_prices_table(prices: Mapping[int, Decimal] | None) -> str:
    if not prices:
        return "<code>-</code>"
    return "\n".join(
        f"<code>{size}</code>  <code>{format_money(prices[size])}</code>"
        for size in sorted(prices, key=int)
    )
