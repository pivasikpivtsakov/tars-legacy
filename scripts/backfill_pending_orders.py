import asyncio
import logging

from common.db import create_pool
from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    async with create_pool() as pool:
        redis = create_redis()
        pending = PendingOrdersRepository(redis=redis)
        offers = OrderOfferRepository(pool=pool)
        orders = OrderRepository(pool=pool)
        try:
            counts = await offers.offered_counts_by_user()
            for user_id, taken in (await orders.taken_counts_by_user()).items():
                counts[user_id] = counts.get(user_id, 0) + taken
            await pending.reset()
            await pending.set_counts(counts=counts)
            logger.info("pending orders backfill complete users=%d", len(counts))
        finally:
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
