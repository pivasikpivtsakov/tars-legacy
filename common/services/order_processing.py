import logging
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from functools import cmp_to_key

import asyncpg

from common.packages import PACKAGE_UNIT_COUNT
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import Order, OrderRepository
from common.repositories.user_profiles import (
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


def _refusal_rate(*, completed: int, cancelled: int, not_picked: int) -> float:
    failures = cancelled + not_picked
    total = completed + failures
    if total == 0:
        return 0.0
    return failures / total


def _speed_rank(seconds: int | None) -> float:
    return float("inf") if seconds is None else float(seconds)


def _price_close(a: int, b: int) -> bool:
    return abs(a - b) <= _PRICE_TOLERANCE * min(a, b)


def _compare_candidates(a: RankedCandidate, b: RankedCandidate) -> int:
    if not _price_close(a.full_price, b.full_price):
        return -1 if a.full_price < b.full_price else 1
    a_speed, b_speed = _speed_rank(a.speed_seconds), _speed_rank(b.speed_seconds)
    if a_speed != b_speed:
        return -1 if a_speed < b_speed else 1
    if a.refusal_rate != b.refusal_rate:
        return -1 if a.refusal_rate < b.refusal_rate else 1
    if a.user_id != b.user_id:
        return -1 if a.user_id < b.user_id else 1
    return 0


class OrderManager:
    def __init__(self, *, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

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
        candidates = [
            RankedCandidate(
                user_id=row.user_id,
                full_price=row.price_60 * decomposition.total_units,
                speed_seconds=row.speed_seconds,
                refusal_rate=_refusal_rate(
                    completed=row.completed,
                    cancelled=row.cancelled,
                    not_picked=row.not_picked,
                ),
            )
            for row in rows
            if row.user_id not in excluded
        ]
        candidates.sort(key=cmp_to_key(_compare_candidates))
        return candidates


class OrderLifecycle:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        orders: OrderRepository,
        offers: OrderOfferRepository,
        profiles: UserProfileRepository,
    ) -> None:
        self._pool = pool
        self._orders = orders
        self._offers = offers
        self._profiles = profiles

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
            await self._offers.expire_offered(order_id=order_id, conn=conn)
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
            return order

    async def cancel(self, *, order_id: int, user_id: int) -> Order | None:
        order = await self._orders.cancel(order_id=order_id, user_id=user_id)
        if order is None:
            return None
        await forward_to_third_party(order=order)
        return order
