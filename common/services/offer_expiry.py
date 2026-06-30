import asyncio
import contextlib
from collections.abc import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.repositories.postgres.order_offers import OrderOfferRepository
from common.repositories.redis.offer_deadlines import OfferDeadline
from common.repositories.redis.pending_orders import PendingOrdersRepository
from common.repositories.redis.rating import RatingRepository
from common.services.dispatch_signal import DispatchSignal

_MAX_CONCURRENT_EDITS = 20


class OfferExpiryService:
    def __init__(
        self,
        *,
        offers: OrderOfferRepository,
        rating: RatingRepository,
        pending: PendingOrdersRepository,
        bot: Bot,
        dispatch: DispatchSignal,
    ) -> None:
        self._offers = offers
        self._rating = rating
        self._pending = pending
        self._bot = bot
        self._dispatch = dispatch

    async def expire_offers(self, *, deadlines: Sequence[OfferDeadline]) -> None:
        if not deadlines:
            return
        expired = await self._offers.expire_many(
            offers=[(deadline.order_id, deadline.user_id) for deadline in deadlines],
        )
        if not expired:
            return
        expired_user_ids = [user_id for _, user_id in expired]
        await self._rating.record_not_taken(user_ids=expired_user_ids)
        await self._pending.release_many(user_ids=expired_user_ids)
        await self._dispatch.request()
        await self._edit_expired_messages(deadlines=deadlines, expired=expired)

    async def _edit_expired_messages(
        self,
        *,
        deadlines: Sequence[OfferDeadline],
        expired: Sequence[tuple[int, int]],
    ) -> None:
        by_key = {(deadline.order_id, deadline.user_id): deadline for deadline in deadlines}
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EDITS)

        async def _edit(deadline: OfferDeadline) -> None:
            async with semaphore:
                with contextlib.suppress(TelegramAPIError):
                    await self._bot.edit_message_text(
                        text=deadline.expired_text,
                        chat_id=deadline.chat_id,
                        message_id=deadline.message_id,
                        reply_markup=None,
                    )

        await asyncio.gather(*(_edit(by_key[key]) for key in expired))
