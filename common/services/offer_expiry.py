import asyncio
import contextlib
from collections.abc import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.repositories.offer_deadlines import OfferDeadline
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.services.dispatch_signal import DispatchSignal

_MAX_CONCURRENT_EDITS = 20


async def expire_offers(
    *,
    offers: OrderOfferRepository,
    rating: RatingRepository,
    pending: PendingOrdersRepository,
    bot: Bot,
    dispatch: DispatchSignal,
    deadlines: Sequence[OfferDeadline],
) -> None:
    if not deadlines:
        return
    expired = await offers.expire_many(
        offers=[(deadline.order_id, deadline.user_id) for deadline in deadlines],
    )
    if not expired:
        return
    expired_user_ids = [user_id for _, user_id in expired]
    await rating.record_not_taken(user_ids=expired_user_ids)
    await pending.release_many(user_ids=expired_user_ids)
    await dispatch.request()
    await _edit_expired_messages(bot=bot, deadlines=deadlines, expired=expired)


async def _edit_expired_messages(
    *,
    bot: Bot,
    deadlines: Sequence[OfferDeadline],
    expired: Sequence[tuple[int, int]],
) -> None:
    by_key = {(deadline.order_id, deadline.user_id): deadline for deadline in deadlines}
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EDITS)

    async def _edit(deadline: OfferDeadline) -> None:
        async with semaphore:
            with contextlib.suppress(TelegramAPIError):
                await bot.edit_message_text(
                    text=deadline.expired_text,
                    chat_id=deadline.chat_id,
                    message_id=deadline.message_id,
                    reply_markup=None,
                )

    await asyncio.gather(*(_edit(by_key[key]) for key in expired))
