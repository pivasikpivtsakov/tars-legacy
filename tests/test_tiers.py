from collections.abc import Sequence

import pytest

from common.catalog.packages import PACKAGE_SIZES
from common.catalog.tiers import (
    Tier,
    allowed_packs_for_tier,
    required_tier,
    tier_allows_units,
    tier_range_label,
    tiers_serving,
)


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([325], Tier.T0),
        ([326], Tier.T1),
        ([1800], Tier.T1),
        ([1801], Tier.T2),
        ([8100], Tier.T2),
        ([8101], None),
        ([59], None),
        ([60, 325], Tier.T0),
        ([60, 326], Tier.T1),
    ],
)
def test_required_tier_boundaries(amounts: Sequence[int], expected: Tier | None) -> None:
    assert required_tier(amounts) is expected


@pytest.mark.parametrize(
    ("tier", "amounts", "expected"),
    [
        (Tier.T0, [60, 325], True),
        (Tier.T0, [60, 326], False),
        (Tier.T0, [59], False),
        (Tier.T1, [1800], True),
        (Tier.T1, [1801], False),
        (Tier.T2, [8100], True),
        (Tier.T2, [8101], False),
    ],
)
def test_tier_allows_units(tier: Tier, amounts: Sequence[int], expected: bool) -> None:
    assert tier_allows_units(tier=tier, amounts=amounts) is expected


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([60], [Tier.T0, Tier.T1, Tier.T2]),
        ([325], [Tier.T0, Tier.T1, Tier.T2]),
        ([326], [Tier.T1, Tier.T2]),
        ([60, 1800], [Tier.T1, Tier.T2]),
        ([1801], [Tier.T2]),
        ([8101], []),
        ([59], []),
    ],
)
def test_tiers_serving(amounts: Sequence[int], expected: list[Tier]) -> None:
    assert tiers_serving(amounts) == expected


def test_allowed_packs_for_tier() -> None:
    assert allowed_packs_for_tier(Tier.T0) == (60, 325)
    assert allowed_packs_for_tier(Tier.T1) == (60, 325, 660, 1800)
    assert allowed_packs_for_tier(Tier.T2) == PACKAGE_SIZES


def test_tier_range_label() -> None:
    assert tier_range_label(Tier.T0) == "60-325"
    assert tier_range_label(Tier.T1) == "60-1800"
    assert tier_range_label(Tier.T2) == "60-8100"
