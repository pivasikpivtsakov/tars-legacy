import asyncio
import logging

from common.db import create_pool
from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    async with create_pool() as pool:
        redis = create_redis()
        online_price_index = OnlinePriceIndex(redis=redis)
        profiles = UserProfileRepository(pool=pool)
        try:
            await online_price_index.clear()
            rankable = await profiles.list_rankable()
            for profile in rankable:
                await online_price_index.sync(profile=profile)
            logger.info("online price index backfill complete users=%d", len(rankable))
        finally:
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
