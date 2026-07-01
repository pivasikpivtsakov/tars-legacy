import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

import asyncpg

from common.catalog.tiers import CODE_TIERS, PACK_TIERS
from common.models.orders import Order
from common.models.rating import RatingStats
from common.models.transactions import TransactionKind
from common.models.user_profiles import UserProfile
from common.repositories.postgres.transactions import TransactionsRepository
from common.repositories.redis.code_order_price import CodeOrderPriceRepository
from common.repositories.redis.online_index import (
    CodeOnlineIndex,
    OnlineIndexRouter,
    PackOnlineIndex,
    PricedCandidate,
)
from common.repositories.redis.rating import RatingRepository
from common.services.order_processing import decompose_amount, full_price_for

_PRICE_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    user_id: int
    full_price: Decimal


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


def _pack_sort_key(
    row: PricedCandidate,
    stats: RatingStats,
) -> tuple[float, float, int, Decimal, int]:
    return (
        _speed_rank(stats.speed_seconds),
        _refusal_rate(
            complete=stats.complete,
            incomplete=stats.incomplete,
            not_taken=stats.not_taken,
        ),
        -stats.complete,
        row.full_price,
        row.user_id,
    )


def _unused_codes(order: Order) -> dict[str, int]:
    raw = order.unused_codes
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not raw:
        return {}
    return {str(code): int(amount) for code, amount in raw.items()}


def _code_amounts(order: Order) -> list[int]:
    return list(_unused_codes(order).values())


class _SweepCache:
    def __init__(self) -> None:
        self._futures: dict[object, asyncio.Future] | None = None

    def begin(self) -> None:
        self._futures = {}

    def end(self) -> None:
        self._futures = None

    async def fetch[T](self, *, key: object, loader: Callable[[], Awaitable[list[T]]]) -> list[T]:
        futures = self._futures
        if futures is None:
            return await loader()
        future = futures.get(key)
        if future is None:
            # Register the future before awaiting so concurrent orders sharing a
            # key await one fetch instead of each issuing their own.
            future = asyncio.ensure_future(loader())
            futures[key] = future
        return await future


class RankingStrategy(ABC):
    def __init__(self) -> None:
        self._sweep = _SweepCache()

    def begin_sweep(self) -> None:
        self._sweep.begin()

    def end_sweep(self) -> None:
        self._sweep.end()

    @abstractmethod
    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: Collection[int],
    ) -> list[RankedCandidate]: ...

    @abstractmethod
    def validate_take(self, *, order: Order, profile: UserProfile) -> bool: ...

    @abstractmethod
    async def taken_price(self, *, order: Order, profile: UserProfile) -> Decimal: ...

    @abstractmethod
    async def on_complete(
        self,
        *,
        order: Order,
        profile: UserProfile,
        conn: asyncpg.Connection,
    ) -> None: ...

    @abstractmethod
    async def on_cancel(self, *, user_id: int) -> None: ...


class PackRankingStrategy(RankingStrategy):
    def __init__(
        self,
        *,
        pack_index: PackOnlineIndex,
        rating: RatingRepository,
        transactions: TransactionsRepository,
    ) -> None:
        super().__init__()
        self._pack_index = pack_index
        self._rating = rating
        self._transactions = transactions
        self._rating_cache: dict[int, RatingStats] | None = None

    def begin_sweep(self) -> None:
        super().begin_sweep()
        self._rating_cache = {}

    def end_sweep(self) -> None:
        super().end_sweep()
        self._rating_cache = None

    async def _rating_stats(self, *, user_ids: list[int]) -> dict[int, RatingStats]:
        cache = self._rating_cache
        if cache is None:
            return await self._rating.get_many(user_ids=user_ids)
        missing = [user_id for user_id in user_ids if user_id not in cache]
        if missing:
            cache.update(await self._rating.get_many(user_ids=missing))
        return {user_id: cache[user_id] for user_id in user_ids}

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: Collection[int],
    ) -> list[RankedCandidate]:
        decomposition = decompose_amount(order.amount)
        package_counts = decomposition.package_counts
        rows = await self._sweep.fetch(
            key=decomposition.counts,
            loader=lambda: self._pack_index.get_cheapest_candidates(package_counts=package_counts),
        )
        excluded = set(exclude_user_ids)
        rows = [row for row in rows if row.user_id not in excluded]
        rows = await self._apply_tier_filter(rows=rows, pack_sizes=list(package_counts))
        if not rows:
            return []
        bucket = _cheapest_price_bucket(rows)
        stats = await self._rating_stats(user_ids=[row.user_id for row in bucket])
        bucket.sort(key=lambda row: _pack_sort_key(row, stats[row.user_id]))
        return [RankedCandidate(user_id=row.user_id, full_price=row.full_price) for row in bucket]

    async def _apply_tier_filter(
        self,
        *,
        rows: list[PricedCandidate],
        pack_sizes: Sequence[int],
    ) -> list[PricedCandidate]:
        required = PACK_TIERS.required(pack_sizes)
        if not rows or required is None or required <= PACK_TIERS.default():
            return rows
        allowed = await self._pack_index.filter_by_min_tier(
            user_ids=[row.user_id for row in rows],
            min_tier=int(required),
        )
        return [row for row in rows if row.user_id in allowed]

    def validate_take(self, *, order: Order, profile: UserProfile) -> bool:
        pack_sizes = list(decompose_amount(order.amount).package_counts)
        if not profile.tier.allows(pack_sizes):
            return False
        prices = profile.prices
        return bool(prices) and all(size in prices for size in pack_sizes)

    async def taken_price(self, *, order: Order, profile: UserProfile) -> Decimal:
        counts = decompose_amount(order.amount).package_counts
        return full_price_for(prices=profile.prices, counts=counts)

    async def on_complete(
        self,
        *,
        order: Order,
        profile: UserProfile,
        conn: asyncpg.Connection,
    ) -> None:
        counts = decompose_amount(order.amount).package_counts
        prices = profile.prices or {}
        await self._transactions.record_credit(
            profile_id=profile.id,
            order_id=order.id,
            kind=TransactionKind.PACK,
            amount=full_price_for(prices=prices, counts=counts),
            details={str(size): count for size, count in counts.items()},
            conn=conn,
        )
        if order.taken_at is not None and order.closed_at is not None:
            await self._rating.record_completion(
                user_id=profile.id,
                taken_at=order.taken_at,
                closed_at=order.closed_at,
            )

    async def on_cancel(self, *, user_id: int) -> None:
        await self._rating.record_cancellation(user_id=user_id)


class CodeRankingStrategy(RankingStrategy):
    def __init__(
        self,
        *,
        code_index: CodeOnlineIndex,
        transactions: TransactionsRepository,
        code_order_price: CodeOrderPriceRepository,
    ) -> None:
        super().__init__()
        self._code_index = code_index
        self._transactions = transactions
        self._code_order_price = code_order_price

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: Collection[int],
    ) -> list[RankedCandidate]:
        tiers = CODE_TIERS.serving(_code_amounts(order))
        if not tiers:
            return []
        candidates = await self._sweep.fetch(
            key=tuple(tiers),
            loader=lambda: self._code_index.get_candidates(tiers=tiers),
        )
        excluded = set(exclude_user_ids)
        full_price = await self._code_order_price.get()
        return [
            RankedCandidate(user_id=candidate.user_id, full_price=full_price)
            for candidate in candidates
            if candidate.user_id not in excluded
        ]

    def validate_take(self, *, order: Order, profile: UserProfile) -> bool:
        if not profile.with_codes:
            return False
        return profile.tier.allows(_code_amounts(order))

    async def taken_price(self, *, order: Order, profile: UserProfile) -> Decimal:  # noqa: ARG002
        return await self._code_order_price.get()

    async def on_complete(
        self,
        *,
        order: Order,
        profile: UserProfile,
        conn: asyncpg.Connection,
    ) -> None:
        await self._transactions.record_credit(
            profile_id=profile.id,
            order_id=order.id,
            kind=TransactionKind.CODE,
            amount=await self._code_order_price.get(),
            details=_unused_codes(order),
            conn=conn,
        )

    async def on_cancel(self, *, user_id: int) -> None:
        pass


def build_strategies(
    *,
    online_index: OnlineIndexRouter,
    rating: RatingRepository,
    transactions: TransactionsRepository,
    code_order_price: CodeOrderPriceRepository,
) -> Mapping[bool, RankingStrategy]:
    return {
        False: PackRankingStrategy(
            pack_index=online_index.pack,
            rating=rating,
            transactions=transactions,
        ),
        True: CodeRankingStrategy(
            code_index=online_index.code,
            transactions=transactions,
            code_order_price=code_order_price,
        ),
    }
