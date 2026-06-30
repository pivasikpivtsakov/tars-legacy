import asyncio
import contextlib
import logging
import time

from common.bot import create_bot
from common.db import create_pool
from common.environment import (
    OFFER_EXPIRY_POLL_SECONDS,
    RATING_SPEED_WINDOW,
    TELEGRAM_BOT_TOKEN,
)
from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.postgres.order_offers import OrderOfferRepository
from common.repositories.redis.offer_deadlines import OfferDeadlineQueue
from common.repositories.redis.pending_orders import PendingOrdersRepository
from common.repositories.redis.rating import RatingRepository
from common.services.dispatch_signal import DispatchSignal
from common.services.offer_expiry import OfferExpiryService

logger = logging.getLogger(__name__)

_CLAIM_BATCH = 100


async def main() -> None:
    setup_logging()
    async with create_pool() as pool:
        redis = create_redis()
        bot = create_bot(token=TELEGRAM_BOT_TOKEN)
        offers = OrderOfferRepository(pool=pool)
        rating = RatingRepository(redis=redis, speed_window=RATING_SPEED_WINDOW)
        pending = PendingOrdersRepository(redis=redis)
        deadlines = OfferDeadlineQueue(redis=redis)
        dispatch = DispatchSignal(redis=redis)
        expiry = OfferExpiryService(
            offers=offers,
            rating=rating,
            pending=pending,
            bot=bot,
            dispatch=dispatch,
        )

        logger.info("starting offer expirer")
        try:
            while True:
                due = await deadlines.claim_due(now_ts=time.time(), limit=_CLAIM_BATCH)
                try:
                    await expiry.expire_offers(deadlines=due)
                except Exception:
                    logger.exception("offer expiry batch failed (count=%d)", len(due))
                await asyncio.sleep(OFFER_EXPIRY_POLL_SECONDS)
        finally:
            await bot.session.close()
            await redis.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
