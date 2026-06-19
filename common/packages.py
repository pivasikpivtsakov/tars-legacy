from collections.abc import Mapping

PACKAGE_UNIT_COUNT: dict[int, int] = {
    60: 1,
    325: 5,
    660: 10,
    1800: 25,
    3850: 50,
    8100: 100,
}

PACKAGE_SIZES: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT))

BASE_UNIT_PRICE_CAP = 1000

PACKAGE_PRICE_LIMIT: dict[int, int] = {
    size: BASE_UNIT_PRICE_CAP * units for size, units in PACKAGE_UNIT_COUNT.items()
}


def format_prices(prices: Mapping[int, int] | None) -> str:
    if not prices:
        return "-"
    return ", ".join(f"{size}={prices[size]}" for size in sorted(prices, key=int))
