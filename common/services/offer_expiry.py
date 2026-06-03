import contextlib
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from common.environment import OFFER_TTL_SECONDS
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.rating import RatingRepository


async def expire_order_offer(
    *,
    bot: Bot,
    offers: OrderOfferRepository,
    rating: RatingRepository,
    order_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    expired_text: str,
) -> None:
    expired_offer = await offers.expire_one(order_id=order_id, user_id=user_id)
    if expired_offer is None:
        return
    await rating.record_not_taken(user_ids=[user_id])
    with contextlib.suppress(TelegramAPIError):
        await bot.edit_message_text(
            text=expired_text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )


def schedule_offer_expiry(
    *,
    scheduler: AsyncIOScheduler,
    bot: Bot,
    offers: OrderOfferRepository,
    rating: RatingRepository,
    order_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    expired_text: str,
) -> None:
    scheduler.add_job(
        expire_order_offer,
        trigger="date",
        run_date=datetime.now(UTC) + timedelta(seconds=OFFER_TTL_SECONDS),
        kwargs={
            "bot": bot,
            "offers": offers,
            "rating": rating,
            "order_id": order_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "expired_text": expired_text,
        },
        id=f"offer_expiry:{order_id}:{user_id}",
        replace_existing=True,
        misfire_grace_time=OFFER_TTL_SECONDS,
    )
