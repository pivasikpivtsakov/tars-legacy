import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from common.repositories.orders import Order, OrderStatus
from common.repositories.rating import RatingStats
from common.repositories.user_profiles import CandidateRow
from common.services.order_processing import (
    OrderManager,
    RankedCandidate,
    _cheapest_price_bucket,
    _ranking_key,
)


def _candidate(
    *,
    user_id: int,
    full_price: int = 100,
    speed_seconds: int | None = 10,
    refusal_rate: float = 0.0,
    complete: int = 0,
) -> RankedCandidate:
    return RankedCandidate(
        user_id=user_id,
        full_price=full_price,
        speed_seconds=speed_seconds,
        refusal_rate=refusal_rate,
        complete=complete,
    )


def _make_order(*, amount: int) -> Order:
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
        unused_codes=None,
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
    )


class _FakeProfiles:
    def __init__(self, *, rows: Sequence[CandidateRow]) -> None:
        self._rows = list(rows)
        self.requested_packages: Sequence[int] | None = None

    async def list_online_with_packages(
        self,
        *,
        required_packages: Sequence[int],
    ) -> list[CandidateRow]:
        self.requested_packages = required_packages
        return list(self._rows)


class _FakeRating:
    def __init__(self, *, stats: dict[int, RatingStats]) -> None:
        self._stats = stats
        self.requested_user_ids: list[int] | None = None

    async def get_many(
        self,
        *,
        user_ids: Sequence[int],
    ) -> dict[int, RatingStats]:
        self.requested_user_ids = list(user_ids)
        return {user_id: self._stats[user_id] for user_id in user_ids}


@pytest.mark.parametrize(
    ("prices", "expected_bucket"),
    [
        ([100, 101, 102, 200], [100, 101]),  # threshold 100 * 1.01 = 101.0
        ([100], [100]),
        ([100, 100, 100], [100, 100, 100]),
        ([200, 100, 101], [100, 101]),  # robust to unsorted input
    ],
)
def test_cheapest_price_bucket(
    prices: list[int],
    expected_bucket: list[int],
) -> None:
    rows = [
        CandidateRow(user_id=index, price_60=price)
        for index, price in enumerate(prices)
    ]
    bucket = _cheapest_price_bucket(rows)
    assert sorted(row.price_60 for row in bucket) == sorted(expected_bucket)


def test_ranking_prefers_faster_speed() -> None:
    candidates = [
        _candidate(user_id=1, speed_seconds=100),
        _candidate(user_id=2, speed_seconds=10),
    ]
    ordered = sorted(candidates, key=_ranking_key)
    assert [c.user_id for c in ordered] == [2, 1]


def test_ranking_unknown_speed_ranks_last() -> None:
    candidates = [
        _candidate(user_id=1, speed_seconds=None),
        _candidate(user_id=2, speed_seconds=999),
    ]
    ordered = sorted(candidates, key=_ranking_key)
    assert [c.user_id for c in ordered] == [2, 1]


def test_ranking_breaks_speed_tie_by_refusal_then_completions() -> None:
    candidates = [
        _candidate(user_id=1, speed_seconds=50, refusal_rate=0.1, complete=2),
        _candidate(user_id=2, speed_seconds=50, refusal_rate=0.1, complete=9),
        _candidate(user_id=3, speed_seconds=50, refusal_rate=0.0, complete=0),
    ]
    ordered = sorted(candidates, key=_ranking_key)
    assert [c.user_id for c in ordered] == [3, 2, 1]


def test_ranking_is_total_order_on_quality_ties() -> None:
    candidates = [
        _candidate(user_id=7, full_price=101),
        _candidate(user_id=3, full_price=100),
        _candidate(user_id=5, full_price=100),
    ]
    ordered = sorted(candidates, key=_ranking_key)
    assert [c.user_id for c in ordered] == [3, 5, 7]


def test_select_candidates_only_fetches_cheapest_bucket() -> None:
    profiles = _FakeProfiles(
        rows=[
            CandidateRow(user_id=1, price_60=100),
            CandidateRow(user_id=2, price_60=101),
            CandidateRow(user_id=3, price_60=102),
            CandidateRow(user_id=4, price_60=200),
        ],
    )
    rating = _FakeRating(
        stats={
            1: RatingStats(speed_seconds=50, complete=1, incomplete=0, not_taken=0),
            2: RatingStats(speed_seconds=10, complete=1, incomplete=0, not_taken=0),
        },
    )
    manager = OrderManager(profiles=profiles, rating=rating)

    result = asyncio.run(manager.select_candidates(order=_make_order(amount=60)))

    assert profiles.requested_packages == (60,)
    assert rating.requested_user_ids == [1, 2]
    assert [c.user_id for c in result] == [2, 1]


def test_select_candidates_empty_skips_rating_lookup() -> None:
    profiles = _FakeProfiles(rows=[])
    rating = _FakeRating(stats={})
    manager = OrderManager(profiles=profiles, rating=rating)

    result = asyncio.run(manager.select_candidates(order=_make_order(amount=60)))

    assert result == []
    assert rating.requested_user_ids is None


def test_select_candidates_excludes_user_ids() -> None:
    profiles = _FakeProfiles(
        rows=[
            CandidateRow(user_id=1, price_60=100),
            CandidateRow(user_id=2, price_60=100),
        ],
    )
    rating = _FakeRating(
        stats={
            2: RatingStats(speed_seconds=10, complete=0, incomplete=0, not_taken=0),
        },
    )
    manager = OrderManager(profiles=profiles, rating=rating)

    result = asyncio.run(
        manager.select_candidates(
            order=_make_order(amount=60),
            exclude_user_ids=[1],
        ),
    )

    assert rating.requested_user_ids == [2]
    assert [c.user_id for c in result] == [2]
