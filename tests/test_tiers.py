import pytest

from common.catalog.packages import PACKAGE_SIZES
from common.catalog.tiers import (
    Tier,
    allowed_packages_for_tier,
    max_package_for_tier,
    required_tier,
    tier_allows,
)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (1, Tier.BASIC),
        (720, Tier.BASIC),
        (721, Tier.STANDARD),
        (16200, Tier.STANDARD),
        (16201, Tier.UNLIMITED),
        (10**9, Tier.UNLIMITED),
    ],
)
def test_required_tier_boundaries(amount: int, expected: Tier) -> None:
    assert required_tier(amount) is expected


@pytest.mark.parametrize(
    ("tier", "amount", "expected"),
    [
        (Tier.BASIC, 720, True),
        (Tier.BASIC, 721, False),
        (Tier.STANDARD, 16200, True),
        (Tier.STANDARD, 16201, False),
        (Tier.UNLIMITED, 10**9, True),
    ],
)
def test_tier_allows(tier: Tier, amount: int, expected: bool) -> None:
    assert tier_allows(tier=tier, amount=amount) is expected


def test_allowed_packages_for_basic_caps_at_660() -> None:
    allowed = allowed_packages_for_tier(Tier.BASIC)
    assert allowed == (60, 325, 660)
    assert max_package_for_tier(Tier.BASIC) == max(allowed)


def test_allowed_packages_for_higher_tiers_is_all_packages() -> None:
    assert allowed_packages_for_tier(Tier.STANDARD) == PACKAGE_SIZES
    assert allowed_packages_for_tier(Tier.UNLIMITED) == PACKAGE_SIZES
    assert max_package_for_tier(Tier.UNLIMITED) == max(PACKAGE_SIZES)
