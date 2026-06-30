import asyncio
import logging
import time
from collections.abc import Collection, Mapping

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
from common.rendering.orders import render_no_takers_text, render_offer_text
from common.repositories.offer_deadlines import OfferDeadlineQueue
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import forward_to_third_party
from common.services.ranking import RankingStrategy

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
        strategies: Mapping[bool, RankingStrategy],
        profiles: UserProfileRepository,
        rating: RatingRepository,
        pending: PendingOrdersRepository,
        deadlines: OfferDeadlineQueue,
        excluded_user_ids: frozenset[int],
        moderator_ids: Collection[int],
    ) -> None:
        self._bot = bot
        self._orders = orders
        self._offers = offers
        self._strategies = strategies
        self._profiles = profiles
        self._rating = rating
        self._pending = pending
        self._deadlines = deadlines
        self._excluded_user_ids = excluded_user_ids
        self._moderator_ids = moderator_ids

    async def offer_order_to_next_user(
        self,
        *,
        order: Order,
        already_offered_user_ids: set[int],
    ) -> None:
        ranked_candidates = await self._strategies[order.is_only_w_codes].select_candidates(
            order=order,
            exclude_user_ids={*already_offered_user_ids, *self._excluded_user_ids},
        )

        if not ranked_candidates:
            await self._orders.mark_no_takers(order_id=order.id)
            await forward_to_third_party(original_id=order.original_id)
            await self._notify_moderators_no_takers(order=order)
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
        if not due_orders:
            return
        order_ids = [order.id for order in due_orders]
        expired = await self._offers.expire_offered_for_orders(order_ids=order_ids)
        await self._release_not_taken(user_ids=[user_id for _, user_id in expired])
        offered_by_order = await self._offers.offered_user_ids_many(order_ids=order_ids)

        for strategy in self._strategies.values():
            strategy.begin_sweep()
        semaphore = asyncio.Semaphore(FANOUT_CHUNK_SIZE)

        async def _offer(order: Order) -> None:
            async with semaphore:
                await self.offer_order_to_next_user(
                    order=order,
                    already_offered_user_ids=offered_by_order.get(order.id, set()),
                )

        try:
            await asyncio.gather(*(_offer(order) for order in due_orders))
        finally:
            for strategy in self._strategies.values():
                strategy.end_sweep()

    async def _notify_moderators_no_takers(self, *, order: Order) -> None:
        if not self._moderator_ids:
            return
        text = render_no_takers_text(order=order, gettext=_)
        tg_ids = await self._profiles.get_tg_ids(profile_ids=self._moderator_ids)
        for moderator_id in self._moderator_ids:
            tg_id = tg_ids.get(moderator_id)
            if tg_id is None:
                logger.warning(
                    "cannot resolve tg_id for moderator_id=%s order_id=%s",
                    moderator_id,
                    order.id,
                )
                continue
            try:
                await self._bot.send_message(chat_id=tg_id, text=text)
            except TelegramAPIError:
                logger.exception(
                    "failed to notify moderator_id=%s order_id=%s",
                    moderator_id,
                    order.id,
                )

    async def _rollback_offer(self, *, order_id: int, user_id: int) -> None:
        await self._offers.expire_one(order_id=order_id, user_id=user_id)
        await self._pending.release(user_id=user_id)

    async def _release_not_taken(self, *, user_ids: list[int]) -> None:
        if not user_ids:
            return
        await self._rating.record_not_taken(user_ids=user_ids)
        await self._pending.release_many(user_ids=user_ids)
