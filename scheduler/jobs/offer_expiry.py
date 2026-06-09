from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from common.environment import OFFER_EXPIRY_MISFIRE_GRACE_SECONDS, OFFER_TTL_SECONDS
from common.services.order_fanout import get_fanout_context, run_offer_expiry


async def job__offer_expiry(
    *,
    order_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    expired_text: str,
) -> None:
    await run_offer_expiry(
        ctx=get_fanout_context(),
        order_id=order_id,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        expired_text=expired_text,
    )


def schedule_offer_expiry(
    *,
    scheduler: AsyncIOScheduler,
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
            "order_id": order_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "expired_text": expired_text,
        },
        id=f"offer_expiry:{order_id}:{user_id}",
        replace_existing=True,
        misfire_grace_time=OFFER_EXPIRY_MISFIRE_GRACE_SECONDS,
    )
