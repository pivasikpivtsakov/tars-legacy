import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from common.environment import OFFER_TTL_SECONDS
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository

logger = logging.getLogger(__name__)


async def job__offer_expiry(
    *,
    bot: Bot,
    offers: OrderOfferRepository,
    rating: RatingRepository,
    pending: PendingOrdersRepository,
    order_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    expired_text: str,
) -> None:
    started = time.perf_counter()
    logger.info("offer expiry started order_id=%s user_id=%s", order_id, user_id)

    expired_offer = await offers.expire_one(order_id=order_id, user_id=user_id)
    if expired_offer is not None:
        await rating.record_not_taken(user_ids=[user_id])
        await pending.release(user_id=user_id)
        with contextlib.suppress(TelegramAPIError):
            await bot.edit_message_text(
                text=expired_text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )

    logger.info(
        "offer expiry completed order_id=%s user_id=%s elapsed=%.3fs",
        order_id,
        user_id,
        time.perf_counter() - started,
    )


def schedule_offer_expiry(
    *,
    scheduler: AsyncIOScheduler,
    bot: Bot,
    offers: OrderOfferRepository,
    rating: RatingRepository,
    pending: PendingOrdersRepository,
    order_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    expired_text: str,
) -> None:
    scheduler.add_job(
        job__offer_expiry,
        trigger="date",
        run_date=datetime.now(UTC) + timedelta(seconds=OFFER_TTL_SECONDS),
        kwargs={
            "bot": bot,
            "offers": offers,
            "rating": rating,
            "pending": pending,
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
