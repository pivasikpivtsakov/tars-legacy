from collections.abc import Sequence

import pytest

from common.catalog.packages import PACKAGE_SIZES
from common.catalog.tiers import (
    CODE_TIERS,
    PACK_TIERS,
    Tier,
    TierNumber,
    TierScheme,
    tiers_for,
)


def _numbers(scheme: TierScheme, amounts: Sequence[int]) -> list[int]:
    return [int(tier) for tier in scheme.serving(amounts)]


def _required(scheme: TierScheme, amounts: Sequence[int]) -> int | None:
    tier = scheme.required(amounts)
    return None if tier is None else int(tier)


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([325], 0),
        ([326], 1),
        ([1800], 1),
        ([1801], 2),
        ([8100], 2),
        ([8101], None),
        ([59], None),
        ([60, 325], 0),
        ([60, 326], 1),
    ],
)
def test_code_required(amounts: Sequence[int], expected: int | None) -> None:
    assert _required(CODE_TIERS, amounts) == expected


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([720], 0),
        ([721], 1),
        ([16200], 1),
        ([16201], 2),
        ([10**9], 2),
        ([59], None),
        ([60, 720], 0),
        ([60, 721], 1),
    ],
)
def test_pack_required(amounts: Sequence[int], expected: int | None) -> None:
    assert _required(PACK_TIERS, amounts) == expected


@pytest.mark.parametrize(
    ("number", "amounts", "expected"),
    [
        (TierNumber.T0, [60, 325], True),
        (TierNumber.T0, [60, 326], False),
        (TierNumber.T0, [59], False),
        (TierNumber.T1, [1800], True),
        (TierNumber.T1, [1801], False),
        (TierNumber.T2, [8100], True),
        (TierNumber.T2, [8101], False),
    ],
)
def test_code_allows(number: TierNumber, amounts: Sequence[int], expected: bool) -> None:
    assert CODE_TIERS.tier(number).allows(amounts) is expected


@pytest.mark.parametrize(
    ("number", "amounts", "expected"),
    [
        (TierNumber.T0, [60, 720], True),
        (TierNumber.T0, [721], False),
        (TierNumber.T0, [59], False),
        (TierNumber.T1, [16200], True),
        (TierNumber.T1, [16201], False),
        (TierNumber.T2, [10**9], True),
        (TierNumber.T2, [59], False),
    ],
)
def test_pack_allows(number: TierNumber, amounts: Sequence[int], expected: bool) -> None:
    assert PACK_TIERS.tier(number).allows(amounts) is expected


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([60], [0, 1, 2]),
        ([325], [0, 1, 2]),
        ([326], [1, 2]),
        ([60, 1800], [1, 2]),
        ([1801], [2]),
        ([8101], []),
        ([59], []),
    ],
)
def test_code_serving(amounts: Sequence[int], expected: list[int]) -> None:
    assert _numbers(CODE_TIERS, amounts) == expected


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([60], [0, 1, 2]),
        ([720], [0, 1, 2]),
        ([721], [1, 2]),
        ([16201], [2]),
        ([10**9], [2]),
        ([59], []),
    ],
)
def test_pack_serving(amounts: Sequence[int], expected: list[int]) -> None:
    assert _numbers(PACK_TIERS, amounts) == expected


def test_code_allowed_packs() -> None:
    assert CODE_TIERS.tier(TierNumber.T0).allowed_packs() == (60, 325)
    assert CODE_TIERS.tier(TierNumber.T1).allowed_packs() == (60, 325, 660, 1800)
    assert CODE_TIERS.tier(TierNumber.T2).allowed_packs() == PACKAGE_SIZES


def test_pack_allowed_packs() -> None:
    assert PACK_TIERS.tier(TierNumber.T0).allowed_packs() == (60, 325, 660)
    assert PACK_TIERS.tier(TierNumber.T1).allowed_packs() == PACKAGE_SIZES
    assert PACK_TIERS.tier(TierNumber.T2).allowed_packs() == PACKAGE_SIZES


def test_code_range_label() -> None:
    assert CODE_TIERS.tier(TierNumber.T0).range_label() == "60-325"
    assert CODE_TIERS.tier(TierNumber.T1).range_label() == "60-1800"
    assert CODE_TIERS.tier(TierNumber.T2).range_label() == "60-8100"


def test_pack_range_label() -> None:
    assert PACK_TIERS.tier(TierNumber.T0).range_label() == "60-720"
    assert PACK_TIERS.tier(TierNumber.T1).range_label() == "60-16200"
    assert PACK_TIERS.tier(TierNumber.T2).range_label() == "60-\u221e"


def test_tiers_for_routes_by_with_codes() -> None:
    assert tiers_for(with_codes=True) is CODE_TIERS
    assert tiers_for(with_codes=False) is PACK_TIERS


def test_tier_constructor_resolves_scheme() -> None:
    assert Tier(with_codes=True, number=1) == CODE_TIERS.tier(TierNumber.T1)
    assert Tier(with_codes=False, number=1) == PACK_TIERS.tier(TierNumber.T1)
    assert int(Tier(with_codes=True, number=2)) == int(TierNumber.T2)


def test_scheme_tiers_and_default() -> None:
    assert [int(tier) for tier in PACK_TIERS.tiers()] == [0, 1, 2]
    assert PACK_TIERS.default() == PACK_TIERS.tier(TierNumber.T0)


def test_tier_int_value_and_ordering() -> None:
    low = CODE_TIERS.tier(TierNumber.T0)
    high = CODE_TIERS.tier(TierNumber.T2)
    assert int(high) == int(TierNumber.T2)
    assert high.value == int(TierNumber.T2)
    assert low < high
    assert max(low, high) == high


def test_tier_equality_within_scheme() -> None:
    assert CODE_TIERS.tier(TierNumber.T1) == CODE_TIERS.tier(TierNumber.T1)
    assert CODE_TIERS.tier(TierNumber.T1) != PACK_TIERS.tier(TierNumber.T1)
