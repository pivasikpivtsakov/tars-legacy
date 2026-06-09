import asyncio
import contextlib
import logging
from collections.abc import Collection
from dataclasses import dataclass
from itertools import batched
from typing import Protocol

import asyncpg
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from redis.asyncio import Redis

from common.environment import (
    FANOUT_CHUNK_SIZE,
    MAX_ORDERS_PENDING,
    OFFER_TTL_SECONDS,
    RATING_SPEED_WINDOW,
)
from common.i18n import build_i18n
from common.keyboards.orders import take_inline_kb
from common.models.orders import Order, OrderStatus
from common.rendering.orders import render_offer_text
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import OrderManager, forward_to_third_party

logger = logging.getLogger(__name__)

_i18n = build_i18n()
_ = _i18n.gettext


class ExpiryScheduler(Protocol):
    def __call__(
        self,
        *,
        order_id: int,
        user_id: int,
        chat_id: int,
        message_id: int,
        expired_text: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class FanoutContext:
    bot: Bot
    orders: OrderRepository
    offers: OrderOfferRepository
    profiles: UserProfileRepository
    order_manager: OrderManager
    rating: RatingRepository
    pending: PendingOrdersRepository
    schedule_expiry: ExpiryScheduler
    excluded_user_ids: frozenset[int]


class _FanoutRuntime:
    context: FanoutContext | None = None


def init_fanout_context(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    bot: Bot,
    schedule_expiry: ExpiryScheduler,
    excluded_user_ids: Collection[int],
) -> None:
    rating = RatingRepository(redis=redis, speed_window=RATING_SPEED_WINDOW)
    _FanoutRuntime.context = FanoutContext(
        bot=bot,
        orders=OrderRepository(pool=pool),
        offers=OrderOfferRepository(pool=pool),
        profiles=UserProfileRepository(pool=pool),
        order_manager=OrderManager(
            online_price_index=OnlinePriceIndex(redis=redis),
            rating=rating,
        ),
        rating=rating,
        pending=PendingOrdersRepository(redis=redis),
        schedule_expiry=schedule_expiry,
        excluded_user_ids=frozenset(excluded_user_ids),
    )


def get_fanout_context() -> FanoutContext:
    if _FanoutRuntime.context is None:
        msg = "fanout context is not initialized"
        raise RuntimeError(msg)
    return _FanoutRuntime.context


async def offer_order_to_next_user(*, ctx: FanoutContext, order: Order) -> None:
    if await ctx.offers.has_active_offer(order_id=order.id, ttl_seconds=OFFER_TTL_SECONDS):
        return
    already_offered_user_ids = await ctx.offers.offered_user_ids(order_id=order.id)
    ranked_candidates = await ctx.order_manager.select_candidates(
        order=order,
        exclude_user_ids={*already_offered_user_ids, *ctx.excluded_user_ids},
    )

    if not ranked_candidates:
        await ctx.orders.mark_no_takers(order_id=order.id)
        expired_user_ids = await ctx.offers.expire_offered(order_id=order.id)
        await _release_not_taken(ctx=ctx, user_ids=expired_user_ids)
        await forward_to_third_party(order=order)
        return

    next_recipient = None
    for candidate in ranked_candidates:
        if await ctx.pending.reserve(user_id=candidate.user_id, limit=MAX_ORDERS_PENDING):
            next_recipient = candidate
            break
    if next_recipient is None:
        return

    await ctx.offers.record_offer(order_id=order.id, user_id=next_recipient.user_id)
    tg_id = await ctx.profiles.get_tg_id(profile_id=next_recipient.user_id)
    offer_text = render_offer_text(
        order=order,
        full_price=next_recipient.full_price,
        gettext=_,
    )
    if tg_id is None:
        logger.warning(
            "cannot resolve tg_id order_id=%s user_id=%s",
            order.id,
            next_recipient.user_id,
        )
        await _rollback_offer(ctx=ctx, order_id=order.id, user_id=next_recipient.user_id)
        return
    try:
        sent = await ctx.bot.send_message(
            chat_id=tg_id,
            text=offer_text,
            reply_markup=take_inline_kb(
                order_id=order.id,
                take_text=_("order.btn_take"),
            ),
        )
    except TelegramAPIError:
        logger.exception(
            "failed to deliver offer order_id=%s user_id=%s",
            order.id,
            next_recipient.user_id,
        )
        await _rollback_offer(ctx=ctx, order_id=order.id, user_id=next_recipient.user_id)
        return
    ctx.schedule_expiry(
        order_id=order.id,
        user_id=next_recipient.user_id,
        chat_id=tg_id,
        message_id=sent.message_id,
        expired_text=f"{offer_text}\n{_('order.expired')}",
    )
    await ctx.orders.mark_offering(order_id=order.id)


async def _rollback_offer(*, ctx: FanoutContext, order_id: int, user_id: int) -> None:
    await ctx.offers.expire_one(order_id=order_id, user_id=user_id)
    await ctx.pending.release(user_id=user_id)


async def _release_not_taken(*, ctx: FanoutContext, user_ids: list[int]) -> None:
    if not user_ids:
        return
    await ctx.rating.record_not_taken(user_ids=user_ids)
    await ctx.pending.release_many(user_ids=user_ids)


async def run_offer_expiry(
    *,
    ctx: FanoutContext,
    order_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    expired_text: str,
) -> None:
    if await ctx.offers.expire_one(order_id=order_id, user_id=user_id) is None:
        return
    await _release_not_taken(ctx=ctx, user_ids=[user_id])
    with contextlib.suppress(TelegramAPIError):
        await ctx.bot.edit_message_text(
            text=expired_text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    order = await ctx.orders.get(order_id=order_id)
    if order is not None and order.status in (OrderStatus.PENDING, OrderStatus.OFFERING):
        await offer_order_to_next_user(ctx=ctx, order=order)


async def sweep_and_fan_out(*, ctx: FanoutContext, stale_after_seconds: int) -> None:
    due_orders = await ctx.orders.list_due_for_fanout(stale_after_seconds=stale_after_seconds)
    for chunk in batched(due_orders, FANOUT_CHUNK_SIZE, strict=False):
        await asyncio.gather(
            *(_recover_and_offer(ctx=ctx, order=order) for order in chunk),
        )


async def _recover_and_offer(*, ctx: FanoutContext, order: Order) -> None:
    expired_user_ids = await ctx.offers.expire_offered(order_id=order.id)
    await _release_not_taken(ctx=ctx, user_ids=expired_user_ids)
    await offer_order_to_next_user(ctx=ctx, order=order)
