from collections.abc import Sequence
from enum import IntEnum

from common.catalog.packages import PACKAGE_SIZES


class Tier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2


TIER_RANGES: dict[Tier, tuple[int, int]] = {
    Tier(0): (60, 325),
    Tier(1): (60, 1800),
    Tier(2): (60, 8100),
}

TIER_DEFAULT = Tier(0)


def tier_allows_unit(*, tier: Tier, amount: int) -> bool:
    low, high = TIER_RANGES[tier]
    return low <= amount <= high


def tier_allows_units(*, tier: Tier, amounts: Sequence[int]) -> bool:
    return all(tier_allows_unit(tier=tier, amount=amount) for amount in amounts)


def required_tier(amounts: Sequence[int]) -> Tier | None:
    for tier in Tier:
        if tier_allows_units(tier=tier, amounts=amounts):
            return tier
    return None


def tiers_serving(amounts: Sequence[int]) -> list[Tier]:
    return [tier for tier in Tier if tier_allows_units(tier=tier, amounts=amounts)]


def allowed_packs_for_tier(tier: Tier) -> tuple[int, ...]:
    low, high = TIER_RANGES[tier]
    return tuple(size for size in PACKAGE_SIZES if low <= size <= high)


def tier_range_label(tier: Tier) -> str:
    low, high = TIER_RANGES[tier]
    return f"{low}-{high}"
