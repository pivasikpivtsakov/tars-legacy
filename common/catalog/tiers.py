from enum import IntEnum

from common.catalog.packages import PACKAGE_SIZES


class Tier(IntEnum):
    BASIC = 0
    STANDARD = 1
    UNLIMITED = 2


TIER_DEFAULT = Tier.BASIC

TIER_MAX_AMOUNT: dict[Tier, int | None] = {
    Tier.BASIC: 720,
    Tier.STANDARD: 16200,
    Tier.UNLIMITED: None,
}


def tier_allows(*, tier: Tier, amount: int) -> bool:
    cap = TIER_MAX_AMOUNT[tier]
    return cap is None or amount <= cap


def required_tier(amount: int) -> Tier:
    for tier in Tier:
        if tier_allows(tier=tier, amount=amount):
            return tier
    return Tier.UNLIMITED


def allowed_packages_for_tier(tier: Tier) -> tuple[int, ...]:
    cap = TIER_MAX_AMOUNT[tier]
    if cap is None:
        return PACKAGE_SIZES
    return tuple(size for size in PACKAGE_SIZES if size <= cap)


def max_package_for_tier(tier: Tier) -> int:
    return max(allowed_packages_for_tier(tier))


def tier_cap_label(tier: Tier) -> str:
    cap = TIER_MAX_AMOUNT[tier]
    return "inf" if cap is None else f"<={cap}"
