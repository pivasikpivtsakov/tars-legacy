PACKAGE_UNIT_COUNT: dict[int, int] = {
    60: 1,
    325: 5,
    660: 10,
    1800: 25,
    3850: 50,
    8100: 100,
}

PACKAGE_SIZES: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT))
