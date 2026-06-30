import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import asyncpg
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.catalog.packages import PACKAGE_UNIT_COUNT
from common.environment import MAX_ORDERS_PENDING
from common.exceptions.orders import OrderAmountError
from common.i18n import build_i18n
from common.models.orders import Order
from common.models.user_profiles import UserProfile
from common.repositories.postgres.order_offers import OrderOfferRepository
from common.repositories.postgres.orders import OrderRepository
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.pending_orders import PendingOrdersRepository
from common.repositories.redis.rating import RatingRepository
from common.services.dispatch_signal import DispatchSignal

if TYPE_CHECKING:
    from common.services.ranking import RankingStrategy

logger = logging.getLogger(__name__)

_ = build_i18n().gettext

# Reason recorded automatically when a taken order expires without user action.
TIMEOUT_REASON = "timeout"

_PACKAGE_SIZES_DESC: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT, reverse=True))


@dataclass(frozen=True, slots=True)
class PackageDecomposition:
    counts: tuple[tuple[int, int], ...]

    @property
    def package_counts(self) -> dict[int, int]:
        return dict(self.counts)


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


def full_price_for(*, prices: Mapping[int, Decimal], counts: Mapping[int, int]) -> Decimal:
    return sum(
        (prices[size] * count for size, count in counts.items()),
        Decimal(0),
    )


async def forward_to_third_party(
    *,
    original_id: int,
    reason: str | None = None,
    bot: Bot | None = None,
    chat_id: int | None = None,
) -> None:
    logger.info(
        "third-party hand-off requested original_id=%s reason=%s", original_id, reason
    )
    if bot is None or chat_id is None:
        return
    text = _("order.long_reserve_forwarded").format(
        order_id=original_id,
        reason=reason or "-",
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramAPIError:
        logger.exception(
            "failed to deliver long-reserve notice original_id=%s reason=%s",
            original_id,
            reason,
        )


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
        strategies: Mapping[bool, RankingStrategy],
        bot: Bot,
        long_reserve_chat_id: int | None,
    ) -> None:
        self._pool = pool
        self._orders = orders
        self._offers = offers
        self._profiles = profiles
        self._rating = rating
        self._pending = pending
        self._dispatch = dispatch_signal
        self._strategies = strategies
        self._bot = bot
        self._long_reserve_chat_id = long_reserve_chat_id

    async def get(self, *, order_id: int) -> Order | None:
        return await self._orders.get(order_id=order_id)

    async def take(
        self,
        *,
        order_id: int,
        user_id: int,
        profile: UserProfile,
    ) -> TakeResult:
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
                    if profile.with_codes != order.is_only_w_codes:
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    strategy = self._strategies[order.is_only_w_codes]
                    if not strategy.validate_take(order=order, profile=profile):
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    claimed_offer = await self._offers.mark_taken(
                        order_id=order_id,
                        user_id=user_id,
                        conn=conn,
                    )
                    if claimed_offer is None:
                        raise _TakeAbortError(TakeStatus.UNAVAILABLE)
                    taken_price = strategy.taken_price(order=order, profile=profile)
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
            profile = await self._profiles.get_by_id(profile_id=user_id)
            if profile is not None:
                strategy = self._strategies[order.is_only_w_codes]
                await strategy.on_complete(order=order, profile=profile, conn=conn)
        await self._pending.release(user_id=user_id)
        await self._dispatch.request()
        return order

    async def cancel(self, *, order_id: int, user_id: int, reason: str) -> Order | None:
        order = await self._orders.cancel(order_id=order_id, user_id=user_id, reason=reason)
        if order is None:
            return None
        strategy = self._strategies[order.is_only_w_codes]
        await strategy.on_cancel(user_id=user_id)
        # заказ отправляется в длинный резерв
        await forward_to_third_party(
            original_id=order.original_id,
            reason=reason,
            bot=self._bot,
            chat_id=self._long_reserve_chat_id,
        )
        await self._pending.release(user_id=user_id)
        await self._dispatch.request()
        return order

    async def expire_taken(self, *, order_id: int, user_id: int) -> Order | None:
        order = await self._orders.time_out(
            order_id=order_id, user_id=user_id, reason=TIMEOUT_REASON
        )
        if order is None:
            return None
        await self._rating.record_not_taken(user_ids=[user_id])
        # заказ отправляется в длинный резерв
        await forward_to_third_party(
            original_id=order.original_id,
            reason=TIMEOUT_REASON,
            bot=self._bot,
            chat_id=self._long_reserve_chat_id,
        )
        await self._pending.release(user_id=user_id)
        await self._dispatch.request()
        return order
