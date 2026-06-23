import asyncio
import logging
import time
from itertools import batched

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.environment import (
    FANOUT_CHUNK_SIZE,
    MAX_ORDERS_PENDING,
    OFFER_TTL_SECONDS,
)
from common.i18n import build_i18n
from common.keyboards.orders import take_inline_kb
from common.models.orders import Order
from common.rendering.orders import render_offer_text
from common.repositories.offer_deadlines import OfferDeadlineQueue
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import OrderManager, forward_to_third_party

logger = logging.getLogger(__name__)

_i18n = build_i18n()
_ = _i18n.gettext


class OrderFanoutService:
    def __init__(
        self,
        *,
        bot: Bot,
        orders: OrderRepository,
        offers: OrderOfferRepository,
        profiles: UserProfileRepository,
        order_manager: OrderManager,
        rating: RatingRepository,
        pending: PendingOrdersRepository,
        deadlines: OfferDeadlineQueue,
        excluded_user_ids: frozenset[int],
    ) -> None:
        self._bot = bot
        self._orders = orders
        self._offers = offers
        self._profiles = profiles
        self._order_manager = order_manager
        self._rating = rating
        self._pending = pending
        self._deadlines = deadlines
        self._excluded_user_ids = excluded_user_ids

    async def offer_order_to_next_user(self, *, order: Order) -> None:
        if await self._offers.has_active_offer(order_id=order.id, ttl_seconds=OFFER_TTL_SECONDS):
            return
        already_offered_user_ids = await self._offers.offered_user_ids(order_id=order.id)
        ranked_candidates = await self._order_manager.select_candidates(
            order=order,
            exclude_user_ids={*already_offered_user_ids, *self._excluded_user_ids},
        )

        if not ranked_candidates:
            await self._orders.mark_no_takers(order_id=order.id)
            expired_user_ids = await self._offers.expire_offered(order_id=order.id)
            await self._release_not_taken(user_ids=expired_user_ids)
            await forward_to_third_party(original_id=order.original_id)
            return

        next_recipient = None
        for candidate in ranked_candidates:
            if await self._pending.reserve(user_id=candidate.user_id, limit=MAX_ORDERS_PENDING):
                next_recipient = candidate
                break
        if next_recipient is None:
            return

        await self._offers.record_offer(order_id=order.id, user_id=next_recipient.user_id)
        tg_id = await self._profiles.get_tg_id(profile_id=next_recipient.user_id)
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
            await self._rollback_offer(order_id=order.id, user_id=next_recipient.user_id)
            return
        try:
            sent = await self._bot.send_message(
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
            await self._rollback_offer(order_id=order.id, user_id=next_recipient.user_id)
            return
        await self._deadlines.schedule(
            order_id=order.id,
            user_id=next_recipient.user_id,
            chat_id=tg_id,
            message_id=sent.message_id,
            expired_text=f"{offer_text}\n{_('order.expired')}",
            deadline_ts=time.time() + OFFER_TTL_SECONDS,
        )
        await self._orders.mark_offering(order_id=order.id)

    async def sweep_and_fan_out(self, *, stale_after_seconds: int, limit: int) -> None:
        due_orders = await self._orders.list_due_for_fanout(
            stale_after_seconds=stale_after_seconds,
            limit=limit,
        )
        self._order_manager.begin_sweep()
        try:
            for chunk in batched(due_orders, FANOUT_CHUNK_SIZE, strict=False):
                await asyncio.gather(
                    *(self._recover_and_offer(order=order) for order in chunk),
                )
        finally:
            self._order_manager.end_sweep()

    async def _rollback_offer(self, *, order_id: int, user_id: int) -> None:
        await self._offers.expire_one(order_id=order_id, user_id=user_id)
        await self._pending.release(user_id=user_id)

    async def _release_not_taken(self, *, user_ids: list[int]) -> None:
        if not user_ids:
            return
        await self._rating.record_not_taken(user_ids=user_ids)
        await self._pending.release_many(user_ids=user_ids)

    async def _recover_and_offer(self, *, order: Order) -> None:
        expired_user_ids = await self._offers.expire_offered(order_id=order.id)
        await self._release_not_taken(user_ids=expired_user_ids)
        await self.offer_order_to_next_user(order=order)
