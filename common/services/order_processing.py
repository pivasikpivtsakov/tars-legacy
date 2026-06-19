import asyncio
import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

import asyncpg

from common.catalog.packages import PACKAGE_UNIT_COUNT
from common.catalog.tiers import Tier, required_tier, tier_allows
from common.environment import MAX_ORDERS_PENDING
from common.exceptions.orders import OrderAmountError
from common.models.orders import Order
from common.models.user_profiles import UserProfile
from common.repositories.online_price_index import OnlinePriceIndex, PricedCandidate
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.dispatch_signal import DispatchSignal

logger = logging.getLogger(__name__)

_PACKAGE_SIZES_DESC: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT, reverse=True))
_PRICE_TOLERANCE = 0.01


@dataclass(frozen=True, slots=True)
class PackageDecomposition:
    counts: tuple[tuple[int, int], ...]

    @property
    def package_counts(self) -> dict[int, int]:
        return dict(self.counts)


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    user_id: int
    full_price: int
    speed_seconds: int | None
    refusal_rate: float
    complete: int


class TakeStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    LIMIT_REACHED = "limit_reached"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class TakeResult:
    status: TakeStatus
    order: Order | None = None


def decompose_amount(amount: int) -> PackageDecomposition:
    if amount <= 0:
        msg = f"amount must be positive, got {amount}"
        raise OrderAmountError(msg)
    counts: list[tuple[int, int]] = []
    remaining = amount
    for size in _PACKAGE_SIZES_DESC:
        count, remaining = divmod(remaining, size)
        if count:
            counts.append((size, count))
    if remaining != 0:
        msg = f"cannot decompose amount={amount} into available packages"
        raise OrderAmountError(msg)
    return PackageDecomposition(counts=tuple(sorted(counts)))


def full_price_for(*, prices: Mapping[int, int], counts: Mapping[int, int]) -> int:
    return sum(prices[size] * count for size, count in counts.items())


async def forward_to_third_party(*, original_id: int) -> None:
    logger.info("third-party hand-off requested original_id=%s", original_id)


def _refusal_rate(*, complete: int, incomplete: int, not_taken: int) -> float:
    failures = incomplete + not_taken
    total = complete + failures
    if total == 0:
        return 0.0
    return failures / total


def _speed_rank(seconds: int | None) -> float:
    return float("inf") if seconds is None else float(seconds)


def _cheapest_price_bucket(rows: Sequence[PricedCandidate]) -> list[PricedCandidate]:
    # Everyone within _PRICE_TOLERANCE of the cheapest price is mutually
    # price-equivalent, so the winner can only come from this bucket: ranking it
    # alone avoids loading ratings for providers that price already rules out.
    min_price = min(row.full_price for row in rows)
    threshold = min_price * (1 + _PRICE_TOLERANCE)
    return [row for row in rows if row.full_price <= threshold]


def _ranking_key(candidate: RankedCandidate) -> tuple[float, float, int, int, int]:
    return (
        _speed_rank(candidate.speed_seconds),
        candidate.refusal_rate,
        -candidate.complete,
        candidate.full_price,
        candidate.user_id,
    )


type _CandidateCache = dict[tuple[tuple[int, int], ...], asyncio.Future[list[PricedCandidate]]]


class OrderManager:
    def __init__(
        self,
        *,
        online_price_index: OnlinePriceIndex,
        rating: RatingRepository,
    ) -> None:
        self._online_price_index = online_price_index
        self._rating = rating
        self._candidate_cache: _CandidateCache | None = None

    def begin_sweep(self) -> None:
        self._candidate_cache = {}

    def end_sweep(self) -> None:
        self._candidate_cache = None

    async def _eligible_candidates(
        self,
        *,
        decomposition: PackageDecomposition,
    ) -> list[PricedCandidate]:
        package_counts = decomposition.package_counts
        cache = self._candidate_cache
        if cache is None:
            return await self._online_price_index.get_cheapest_candidates(
                package_counts=package_counts,
            )
        future = cache.get(decomposition.counts)
        if future is None:
            # Register the future before awaiting so concurrent orders sharing a
            # decomposition await one ZINTER instead of each issuing their own.
            future = asyncio.ensure_future(
                self._online_price_index.get_cheapest_candidates(
                    package_counts=package_counts,
                ),
            )
            cache[decomposition.counts] = future
        return await future

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: Collection[int] = (),
    ) -> list[RankedCandidate]:
        decomposition = decompose_amount(order.amount)
        rows = await self._eligible_candidates(decomposition=decomposition)
        excluded = set(exclude_user_ids)
        rows = [row for row in rows if row.user_id not in excluded]
        required = required_tier(order.amount)
        if required > Tier.BASIC and rows:
            allowed = await self._online_price_index.filter_by_min_tier(
                user_ids=[row.user_id for row in rows],
                min_tier=int(required),
            )
            rows = [row for row in rows if row.user_id in allowed]
        if order.is_only_w_codes and rows:
            allowed = await self._online_price_index.filter_with_codes(
                user_ids=[row.user_id for row in rows],
            )
            rows = [row for row in rows if row.user_id in allowed]
        if not rows:
            return []
        bucket = _cheapest_price_bucket(rows)
        stats = await self._rating.get_many(
            user_ids=[row.user_id for row in bucket],
        )
        candidates: list[RankedCandidate] = []
        for row in bucket:
            user_stats = stats[row.user_id]
            candidates.append(
                RankedCandidate(
                    user_id=row.user_id,
                    full_price=row.full_price,
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


class _TakeAbortError(Exception):
    def __init__(self, status: TakeStatus) -> None:
        self.status = status


class OrderLifecycle:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        orders: OrderRepository,
        offers: OrderOfferRepository,
        profiles: UserProfileRepository,
        rating: RatingRepository,
        pending: PendingOrdersRepository,
        dispatch_signal: DispatchSignal,
    ) -> None:
        self._pool = pool
        self._orders = orders
        self._offers = offers
        self._profiles = profiles
        self._rating = rating
        self._pending = pending
        self._dispatch = dispatch_signal

    async def take(
        self,
        *,
        order_id: int,
        user_id: int,
        profile: UserProfile,
    ) -> TakeResult:
        if not profile.prices:
            return TakeResult(status=TakeStatus.UNAVAILABLE)
        async with self._pool.acquire() as conn:
            try:
                async with conn.transaction():
                    is_online = await self._profiles.lock_is_online(
                        profile_id=user_id,
                        conn=conn,
                    )
                    if not is_online:
                        raise _TakeAbortError(TakeStatus.OFFLINE)
                    in_work = await self._orders.count_in_work(user_id=user_id, conn=conn)
                    if in_work >= MAX_ORDERS_PENDING:
                        raise _TakeAbortError(TakeStatus.LIMIT_REACHED)
                    order = await self._orders.get(order_id=order_id, conn=conn)
                    if order is None:
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    if not tier_allows(tier=profile.tier, amount=order.amount):
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    counts = decompose_amount(order.amount).package_counts
                    if any(size not in profile.prices for size in counts):
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    claimed_offer = await self._offers.mark_taken(
                        order_id=order_id,
                        user_id=user_id,
                        conn=conn,
                    )
                    if claimed_offer is None:
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    taken_price = full_price_for(prices=profile.prices, counts=counts)
                    claimed = await self._orders.claim_for_take(
                        order_id=order_id,
                        user_id=user_id,
                        taken_price=taken_price,
                        conn=conn,
                    )
                    if claimed is None:
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    expired_user_ids = await self._offers.expire_offered(
                        order_id=order_id,
                        conn=conn,
                    )
            except _TakeAbortError as abort:
                return TakeResult(status=abort.status)
        await self._rating.record_not_taken(user_ids=expired_user_ids)
        await self._pending.release_many(user_ids=expired_user_ids)
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
                    profile_id=user_id,
                    amount=order.taken_price,
                    conn=conn,
                )
        if order.taken_at is not None and order.closed_at is not None:
            await self._rating.record_completion(
                user_id=user_id,
                taken_at=order.taken_at,
                closed_at=order.closed_at,
            )
        await self._pending.release(user_id=user_id)
        await self._dispatch.request()
        return order

    async def cancel(self, *, order_id: int, user_id: int) -> Order | None:
        order = await self._orders.cancel(order_id=order_id, user_id=user_id)
        if order is None:
            return None
        await self._rating.record_cancellation(user_id=user_id)
        await forward_to_third_party(original_id=order.original_id)
        await self._pending.release(user_id=user_id)
        await self._dispatch.request()
        return order
