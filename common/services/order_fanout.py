import asyncio
import logging
from itertools import batched

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from common.environment import FANOUT_CHUNK_SIZE, MAX_ORDERS_PENDING, OFFER_TTL_SECONDS
from common.i18n import build_i18n
from common.keyboards.orders import take_inline_kb
from common.models.orders import Order
from common.rendering.orders import render_offer_text
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.offer_expiry import schedule_offer_expiry
from common.services.order_processing import OrderManager, forward_to_third_party

logger = logging.getLogger(__name__)

_i18n = build_i18n()
_ = _i18n.gettext


async def offer_order_to_next_user(
    *,
    order: Order,
    bot: Bot,
    orders: OrderRepository,
    offers: OrderOfferRepository,
    profiles: UserProfileRepository,
    order_manager: OrderManager,
    rating: RatingRepository,
    pending: PendingOrdersRepository,
    scheduler: AsyncIOScheduler,
) -> None:
    if await offers.has_active_offer(order_id=order.id, ttl_seconds=OFFER_TTL_SECONDS):
        return
    already_offered_user_ids = await offers.offered_user_ids(order_id=order.id)
    ranked_candidates = await order_manager.select_candidates(
        order=order,
        exclude_user_ids=already_offered_user_ids,
    )

    if not ranked_candidates:
        await orders.mark_no_takers(order_id=order.id)
        expired_user_ids = await offers.expire_offered(order_id=order.id)
        await rating.record_not_taken(user_ids=expired_user_ids)
        await pending.release_many(user_ids=expired_user_ids)
        await forward_to_third_party(order=order)
        return

    next_recipient = None
    for candidate in ranked_candidates:
        if await pending.reserve(user_id=candidate.user_id, limit=MAX_ORDERS_PENDING):
            next_recipient = candidate
            break
    if next_recipient is None:
        return

    await offers.record_offer(order_id=order.id, user_id=next_recipient.user_id)
    tg_id = await profiles.get_tg_id(profile_id=next_recipient.user_id)
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
        await _release_offer(
            offers=offers,
            pending=pending,
            order_id=order.id,
            user_id=next_recipient.user_id,
        )
        return
    try:
        sent = await bot.send_message(
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
        await _release_offer(
            offers=offers,
            pending=pending,
            order_id=order.id,
            user_id=next_recipient.user_id,
        )
        return
    schedule_offer_expiry(
        scheduler=scheduler,
        bot=bot,
        offers=offers,
        rating=rating,
        pending=pending,
        order_id=order.id,
        user_id=next_recipient.user_id,
        chat_id=tg_id,
        message_id=sent.message_id,
        expired_text=f"{offer_text}\n{_('order.expired')}",
    )
    await orders.mark_offering(order_id=order.id)


async def _release_offer(
    *,
    offers: OrderOfferRepository,
    pending: PendingOrdersRepository,
    order_id: int,
    user_id: int,
) -> None:
    await offers.expire_one(order_id=order_id, user_id=user_id)
    await pending.release(user_id=user_id)


async def fan_out_active_orders(
    *,
    bot: Bot,
    orders: OrderRepository,
    offers: OrderOfferRepository,
    profiles: UserProfileRepository,
    order_manager: OrderManager,
    rating: RatingRepository,
    pending: PendingOrdersRepository,
    scheduler: AsyncIOScheduler,
) -> None:
    active_orders = await orders.list_active_for_fanout()
    for chunk in batched(active_orders, FANOUT_CHUNK_SIZE):
        await asyncio.gather(
            *(
                offer_order_to_next_user(
                    order=order,
                    bot=bot,
                    orders=orders,
                    offers=offers,
                    profiles=profiles,
                    order_manager=order_manager,
                    rating=rating,
                    pending=pending,
                    scheduler=scheduler,
                )
                for order in chunk
            ),
        )
