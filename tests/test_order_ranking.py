import asyncio
import json
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from common.catalog.tiers import Tier, TierNumber
from common.models.orders import Order, OrderStatus
from common.models.rating import RatingStats
from common.models.user_profiles import UserProfile, UserProfileStatus
from common.repositories.online_index import CodeCandidate, PricedCandidate
from common.services.order_processing import OrderManager
from common.services.ranking import (
    CodeRankingStrategy,
    PackRankingStrategy,
    RankedCandidate,
    RankingStrategy,
    _cheapest_price_bucket,
)


def _run(
    *,
    strategy: RankingStrategy,
    order: Order,
    exclude: Collection[int] = (),
) -> list[RankedCandidate]:
    return asyncio.run(strategy.select_candidates(order=order, exclude_user_ids=exclude))


def _priced(user_id: int, price: int) -> PricedCandidate:
    return PricedCandidate(user_id=user_id, full_price=Decimal(price))


def _stats(*, speed_seconds: int | None, complete: int = 0, refused: int = 0) -> RatingStats:
    return RatingStats(
        speed_seconds=speed_seconds,
        complete=complete,
        incomplete=0,
        not_taken=refused,
    )


def _pack_order(*, amount: int) -> Order:
    return _order(amount=amount, unused_codes=None, is_only_w_codes=False)


def _code_order(*, codes: Mapping[str, int]) -> Order:
    return _order(
        amount=sum(codes.values()) or 60,
        unused_codes=json.dumps(dict(codes)),
        is_only_w_codes=True,
    )


def _order(*, amount: int, unused_codes: str | None, is_only_w_codes: bool) -> Order:
    now = datetime.now(UTC)
    return Order(
        id=1,
        original_id=1,
        shop_access_key=None,
        status=OrderStatus.PENDING,
        status_reason=None,
        amount=amount,
        pubg_id=None,
        codes=None,
        unused_codes=unused_codes,
        broken_codes=(),
        redeemed_codes=(),
        additional_data=None,
        offered_at=None,
        closed_at=None,
        taken_at=None,
        taken_by=None,
        taken_price=None,
        created_at=now,
        updated_at=now,
        external_status=None,
        is_only_w_codes=is_only_w_codes,
    )


def _profile(
    *,
    user_id: int = 1,
    tier: TierNumber = TierNumber.T0,
    with_codes: bool = False,
    prices: Mapping[int, str] | None = None,
) -> UserProfile:
    raw_prices = None if prices is None else {str(size): value for size, value in prices.items()}
    return UserProfile(
        id=user_id,
        tg_id=user_id,
        chat_addable=True,
        raw_prices=raw_prices,
        withdrawal_method="card",
        work_start=None,
        work_end=None,
        is_online=True,
        with_codes=with_codes,
        status=UserProfileStatus.ACTIVE,
        tier=Tier(with_codes=with_codes, number=tier),
    )


class _FakePackIndex:
    def __init__(
        self,
        *,
        rows: Sequence[PricedCandidate],
        tiers: Mapping[int, int] | None = None,
    ) -> None:
        self._rows = sorted(rows, key=lambda row: (row.full_price, row.user_id))
        self._tiers = dict(tiers or {})
        self.requested_package_counts: Mapping[int, int] | None = None
        self.filter_by_min_tier_calls: list[tuple[list[int], int]] = []

    async def get_cheapest_candidates(
        self,
        *,
        package_counts: Mapping[int, int],
    ) -> list[PricedCandidate]:
        self.requested_package_counts = package_counts
        return list(self._rows)

    async def filter_by_min_tier(self, *, user_ids: Sequence[int], min_tier: int) -> set[int]:
        self.filter_by_min_tier_calls.append((list(user_ids), min_tier))
        return {
            user_id
            for user_id in user_ids
            if (tier := self._tiers.get(user_id)) is not None and tier >= min_tier
        }


class _FakeCodeIndex:
    def __init__(self, *, candidates: Sequence[CodeCandidate]) -> None:
        self._candidates = list(candidates)
        self.requested_tiers: list[list[Tier]] = []

    async def get_candidates(self, *, tiers: Sequence[Tier]) -> list[CodeCandidate]:
        self.requested_tiers.append(list(tiers))
        return list(self._candidates)


def _requested_tier_numbers(calls: Sequence[Sequence[Tier]]) -> list[list[int]]:
    return [[int(tier) for tier in call] for call in calls]


class _FakeRating:
    def __init__(self, *, stats: Mapping[int, RatingStats]) -> None:
        self._stats = dict(stats)
        self.requested_user_ids: list[int] | None = None

    async def get_many(self, *, user_ids: Sequence[int]) -> dict[int, RatingStats]:
        self.requested_user_ids = list(user_ids)
        return {user_id: self._stats[user_id] for user_id in user_ids}


class _FakeTransactions:
    pass


def _pack_strategy(
    *,
    pack_index: _FakePackIndex,
    rating: _FakeRating,
) -> PackRankingStrategy:
    return PackRankingStrategy(
        pack_index=pack_index,
        rating=rating,
        transactions=_FakeTransactions(),
    )


@pytest.mark.parametrize(
    ("prices", "expected_bucket"),
    [
        ([100, 101, 102, 200], [100, 101]),
        ([100], [100]),
        ([100, 100, 100], [100, 100, 100]),
        ([200, 100, 101], [100, 101]),
    ],
)
def test_cheapest_price_bucket(prices: list[int], expected_bucket: list[int]) -> None:
    rows = [_priced(index, price) for index, price in enumerate(prices)]
    bucket = _cheapest_price_bucket(rows)
    assert sorted(row.full_price for row in bucket) == sorted(Decimal(p) for p in expected_bucket)


def test_pack_strategy_only_rates_cheapest_bucket() -> None:
    pack_index = _FakePackIndex(
        rows=[_priced(1, 100), _priced(2, 101), _priced(3, 102), _priced(4, 200)],
    )
    rating = _FakeRating(
        stats={1: _stats(speed_seconds=50), 2: _stats(speed_seconds=10)},
    )
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60))

    assert pack_index.requested_package_counts == {60: 1}
    assert rating.requested_user_ids == [1, 2]
    assert [c.user_id for c in result] == [2, 1]


def test_pack_strategy_prefers_faster_speed() -> None:
    pack_index = _FakePackIndex(rows=[_priced(1, 100), _priced(2, 100)])
    rating = _FakeRating(
        stats={1: _stats(speed_seconds=100), 2: _stats(speed_seconds=10)},
    )
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60))

    assert [c.user_id for c in result] == [2, 1]


def test_pack_strategy_unknown_speed_ranks_last() -> None:
    pack_index = _FakePackIndex(rows=[_priced(1, 100), _priced(2, 100)])
    rating = _FakeRating(
        stats={1: _stats(speed_seconds=None), 2: _stats(speed_seconds=999)},
    )
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60))

    assert [c.user_id for c in result] == [2, 1]


def test_pack_strategy_breaks_speed_tie_by_refusal_then_completions() -> None:
    pack_index = _FakePackIndex(rows=[_priced(1, 100), _priced(2, 100), _priced(3, 100)])
    rating = _FakeRating(
        stats={
            1: _stats(speed_seconds=50, complete=2, refused=2),
            2: _stats(speed_seconds=50, complete=9, refused=9),
            3: _stats(speed_seconds=50, complete=0, refused=0),
        },
    )
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60))

    assert [c.user_id for c in result] == [3, 2, 1]


def test_pack_strategy_excludes_user_ids() -> None:
    pack_index = _FakePackIndex(rows=[_priced(1, 100), _priced(2, 100)])
    rating = _FakeRating(stats={2: _stats(speed_seconds=10)})
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60), exclude=[1])

    assert rating.requested_user_ids == [2]
    assert [c.user_id for c in result] == [2]


def test_pack_strategy_empty_skips_rating_lookup() -> None:
    pack_index = _FakePackIndex(rows=[])
    rating = _FakeRating(stats={})
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60))

    assert result == []
    assert rating.requested_user_ids is None


def test_pack_strategy_tier_zero_order_skips_tier_filter() -> None:
    pack_index = _FakePackIndex(rows=[_priced(1, 100)], tiers={1: 0})
    rating = _FakeRating(stats={1: _stats(speed_seconds=10)})
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=60))

    assert pack_index.filter_by_min_tier_calls == []
    assert [c.user_id for c in result] == [1]


def test_pack_strategy_filters_below_required_tier() -> None:
    pack_index = _FakePackIndex(
        rows=[_priced(1, 100), _priced(2, 100)],
        tiers={1: 0, 2: 1},
    )
    rating = _FakeRating(stats={2: _stats(speed_seconds=10)})
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=1800))

    assert pack_index.filter_by_min_tier_calls == [([1, 2], 1)]
    assert rating.requested_user_ids == [2]
    assert [c.user_id for c in result] == [2]


def test_pack_strategy_largest_pack_requires_t1() -> None:
    # Pack tiers are 60-720 / 60-16200 / 60-unbounded, so the largest current
    # package (8100) only requires T1; no current pack can require T2.
    pack_index = _FakePackIndex(
        rows=[_priced(1, 100), _priced(2, 100), _priced(3, 100)],
        tiers={1: 0, 2: 1, 3: 2},
    )
    rating = _FakeRating(stats={2: _stats(speed_seconds=20), 3: _stats(speed_seconds=10)})
    strategy = _pack_strategy(pack_index=pack_index, rating=rating)

    result = _run(strategy=strategy, order=_pack_order(amount=8100))

    assert pack_index.filter_by_min_tier_calls == [([1, 2, 3], 1)]
    assert [c.user_id for c in result] == [3, 2]


@pytest.mark.parametrize(
    ("tier", "prices", "expected"),
    [
        (TierNumber.T0, {60: "10.00"}, True),
        (TierNumber.T0, {325: "10.00"}, False),
        (TierNumber.T0, None, False),
    ],
)
def test_pack_strategy_validate_take(
    tier: TierNumber,
    prices: Mapping[int, str] | None,
    expected: bool,
) -> None:
    strategy = _pack_strategy(
        pack_index=_FakePackIndex(rows=[]),
        rating=_FakeRating(stats={}),
    )
    profile = _profile(tier=tier, prices=prices)

    assert strategy.validate_take(order=_pack_order(amount=60), profile=profile) is expected


def test_pack_strategy_taken_price_sums_priced_packages() -> None:
    strategy = _pack_strategy(
        pack_index=_FakePackIndex(rows=[]),
        rating=_FakeRating(stats={}),
    )
    profile = _profile(prices={60: "10.00", 325: "40.00"})

    taken = strategy.taken_price(order=_pack_order(amount=385), profile=profile)

    assert taken == Decimal("50.00")


def _code_strategy(*, code_index: _FakeCodeIndex) -> CodeRankingStrategy:
    return CodeRankingStrategy(code_index=code_index, transactions=_FakeTransactions())


def test_code_strategy_orders_by_online_time_and_filters_tiers() -> None:
    code_index = _FakeCodeIndex(
        candidates=[CodeCandidate(user_id=3), CodeCandidate(user_id=1), CodeCandidate(user_id=2)],
    )
    strategy = _code_strategy(code_index=code_index)

    result = _run(strategy=strategy, order=_code_order(codes={"CODE-1": 60, "CODE-2": 325}))

    assert _requested_tier_numbers(code_index.requested_tiers) == [[0, 1, 2]]
    assert [c.user_id for c in result] == [3, 1, 2]


def test_code_strategy_excludes_user_ids() -> None:
    code_index = _FakeCodeIndex(
        candidates=[CodeCandidate(user_id=3), CodeCandidate(user_id=1), CodeCandidate(user_id=2)],
    )
    strategy = _code_strategy(code_index=code_index)

    result = _run(strategy=strategy, order=_code_order(codes={"CODE-1": 326}), exclude=[1])

    assert _requested_tier_numbers(code_index.requested_tiers) == [[1, 2]]
    assert [c.user_id for c in result] == [3, 2]


def test_code_strategy_full_price_is_sum_of_code_amounts() -> None:
    code_index = _FakeCodeIndex(candidates=[CodeCandidate(user_id=1)])
    strategy = _code_strategy(code_index=code_index)

    result = _run(strategy=strategy, order=_code_order(codes={"CODE-1": 60, "CODE-2": 325}))

    assert [c.full_price for c in result] == [Decimal(385)]


def test_code_strategy_code_outside_any_tier_yields_no_candidates() -> None:
    code_index = _FakeCodeIndex(candidates=[CodeCandidate(user_id=1)])
    strategy = _code_strategy(code_index=code_index)

    result = _run(strategy=strategy, order=_code_order(codes={"CODE-1": 8101}))

    assert result == []
    assert code_index.requested_tiers == []


def test_code_strategy_taken_price_is_sum_of_code_amounts() -> None:
    strategy = _code_strategy(code_index=_FakeCodeIndex(candidates=[]))
    profile = _profile(tier=TierNumber.T2, with_codes=True)

    taken = strategy.taken_price(
        order=_code_order(codes={"CODE-1": 60, "CODE-2": 325}),
        profile=profile,
    )

    assert taken == Decimal(385)


@pytest.mark.parametrize(
    ("tier", "with_codes", "expected"),
    [
        (TierNumber.T2, True, True),
        (TierNumber.T2, False, False),
        (TierNumber.T1, True, False),
    ],
)
def test_code_strategy_validate_take(tier: TierNumber, with_codes: bool, expected: bool) -> None:
    strategy = _code_strategy(code_index=_FakeCodeIndex(candidates=[]))
    profile = _profile(tier=tier, with_codes=with_codes)
    order = _code_order(codes={"CODE-1": 1801})

    assert strategy.validate_take(order=order, profile=profile) is expected


def test_order_manager_routes_by_is_only_w_codes() -> None:
    pack_index = _FakePackIndex(rows=[_priced(1, 100)])
    rating = _FakeRating(stats={1: _stats(speed_seconds=10)})
    code_index = _FakeCodeIndex(candidates=[CodeCandidate(user_id=5)])
    manager = OrderManager(
        strategies={
            False: _pack_strategy(pack_index=pack_index, rating=rating),
            True: _code_strategy(code_index=code_index),
        },
    )

    pack_result = asyncio.run(manager.select_candidates(order=_pack_order(amount=60)))
    code_result = asyncio.run(
        manager.select_candidates(order=_code_order(codes={"CODE-1": 60})),
    )

    assert [c.user_id for c in pack_result] == [1]
    assert [c.user_id for c in code_result] == [5]
    assert isinstance(pack_result[0], RankedCandidate)
