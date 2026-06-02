import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum

import asyncpg

from common.packages import PACKAGE_UNIT_COUNT
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import Order, OrderRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import (
    CandidateRow,
    UserProfile,
    UserProfileRepository,
)

logger = logging.getLogger(__name__)

_PACKAGE_SIZES_DESC: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT, reverse=True))
_PRICE_TOLERANCE = 0.01
_MAX_IN_WORK = 3


@dataclass(frozen=True, slots=True)
class PackageDecomposition:
    parts: tuple[int, ...]
    unique_parts: tuple[int, ...]
    total_units: int


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    user_id: int
    full_price: int
    speed_seconds: int | None
    refusal_rate: float
    complete: int


class OrderAmountError(ValueError):
    pass


class TakeStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    LIMIT_REACHED = "limit_reached"


@dataclass(frozen=True, slots=True)
class TakeResult:
    status: TakeStatus
    order: Order | None = None


def decompose_amount(amount: int) -> PackageDecomposition:
    if amount <= 0:
        msg = f"amount must be positive, got {amount}"
        raise OrderAmountError(msg)
    parts: list[int] = []
    remaining = amount
    for size in _PACKAGE_SIZES_DESC:
        count, remaining = divmod(remaining, size)
        parts.extend([size] * count)
    if remaining != 0:
        msg = f"cannot decompose amount={amount} into available packages"
        raise OrderAmountError(msg)
    return PackageDecomposition(
        parts=tuple(parts),
        unique_parts=tuple(sorted(set(parts))),
        total_units=sum(PACKAGE_UNIT_COUNT[p] for p in parts),
    )


async def forward_to_third_party(*, order: Order) -> None:
    logger.info("third-party hand-off requested order_id=%s", order.id)


def _refusal_rate(*, complete: int, incomplete: int, not_taken: int) -> float:
    failures = incomplete + not_taken
    total = complete + failures
    if total == 0:
        return 0.0
    return failures / total


def _speed_rank(seconds: int | None) -> float:
    return float("inf") if seconds is None else float(seconds)


def _cheapest_price_bucket(rows: Sequence[CandidateRow]) -> list[CandidateRow]:
    # Everyone within _PRICE_TOLERANCE of the cheapest price is mutually
    # price-equivalent, so the winner can only come from this bucket: ranking it
    # alone avoids loading ratings for providers that price already rules out.
    min_price = min(row.price_60 for row in rows)
    threshold = min_price * (1 + _PRICE_TOLERANCE)
    return [row for row in rows if row.price_60 <= threshold]


def _ranking_key(candidate: RankedCandidate) -> tuple[float, float, int, int, int]:
    return (
        _speed_rank(candidate.speed_seconds),
        candidate.refusal_rate,
        -candidate.complete,
        candidate.full_price,
        candidate.user_id,
    )


class OrderManager:
    def __init__(
        self,
        *,
        profiles: UserProfileRepository,
        rating: RatingRepository,
    ) -> None:
        self._profiles = profiles
        self._rating = rating

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: Collection[int] = (),
    ) -> list[RankedCandidate]:
        if order.amount is None:
            msg = f"order id={order.id} has no amount"
            raise OrderAmountError(msg)
        decomposition = decompose_amount(order.amount)
        rows = await self._profiles.list_online_with_packages(
            required_packages=decomposition.unique_parts,
        )
        excluded = set(exclude_user_ids)
        eligible = [row for row in rows if row.user_id not in excluded]
        if not eligible:
            return []
        bucket = _cheapest_price_bucket(eligible)
        stats = await self._rating.get_many(
            user_ids=[row.user_id for row in bucket],
        )
        candidates: list[RankedCandidate] = []
        for row in bucket:
            user_stats = stats[row.user_id]
            candidates.append(
                RankedCandidate(
                    user_id=row.user_id,
                    full_price=row.price_60 * decomposition.total_units,
                    speed_seconds=user_stats.speed_seconds,
                    refusal_rate=_refusal_rate(
                        complete=user_stats.complete,
                        incomplete=user_stats.incomplete,
                        not_taken=user_stats.not_taken,
                    ),
                    complete=user_stats.complete,
                ),
            )
        candidates.sort(key=_ranking_key)
        return candidates


class OrderLifecycle:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        orders: OrderRepository,
        offers: OrderOfferRepository,
        profiles: UserProfileRepository,
        rating: RatingRepository,
    ) -> None:
        self._pool = pool
        self._orders = orders
        self._offers = offers
        self._profiles = profiles
        self._rating = rating

    async def take(
        self,
        *,
        order_id: int,
        user_id: int,
        profile: UserProfile,
    ) -> TakeResult:
        if profile.price_60 is None:
            return TakeResult(status=TakeStatus.UNAVAILABLE)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT 1 FROM user_profiles WHERE user_id = $1 FOR UPDATE",
                user_id,
            )
            in_work = await self._orders.count_in_work(user_id=user_id, conn=conn)
            if in_work >= _MAX_IN_WORK:
                return TakeResult(status=TakeStatus.LIMIT_REACHED)
            order = await self._orders.get(order_id=order_id, conn=conn)
            if order is None or order.amount is None:
                return TakeResult(status=TakeStatus.UNAVAILABLE)
            taken_price = profile.price_60 * decompose_amount(order.amount).total_units
            claimed = await self._orders.claim_for_take(
                order_id=order_id,
                user_id=user_id,
                taken_price=taken_price,
                conn=conn,
            )
            if claimed is None:
                return TakeResult(status=TakeStatus.UNAVAILABLE)
            await self._offers.mark_taken(
                order_id=order_id,
                user_id=user_id,
                conn=conn,
            )
            expired_user_ids = await self._offers.expire_offered(
                order_id=order_id,
                conn=conn,
            )
        await self._rating.record_not_taken(user_ids=expired_user_ids)
        return TakeResult(status=TakeStatus.OK, order=claimed)

    async def complete(self, *, order_id: int, user_id: int) -> Order | None:
        async with self._pool.acquire() as conn, conn.transaction():
            order = await self._orders.complete(
                order_id=order_id,
                user_id=user_id,
                conn=conn,
            )
            if order is None:
                return None
            if order.taken_price is not None:
                await self._profiles.credit_balance(
                    user_id=user_id,
                    amount=order.taken_price,
                    conn=conn,
                )
        if order.taken_at is not None and order.closed_at is not None:
            await self._rating.record_completion(
                user_id=user_id,
                taken_at=order.taken_at,
                closed_at=order.closed_at,
            )
        return order

    async def cancel(self, *, order_id: int, user_id: int) -> Order | None:
        order = await self._orders.cancel(order_id=order_id, user_id=user_id)
        if order is None:
            return None
        await self._rating.record_cancellation(user_id=user_id)
        await forward_to_third_party(order=order)
        return order
