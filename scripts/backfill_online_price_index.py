import asyncio
import logging

from common.db import create_pool
from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.online_index import (
    CodeOnlineIndex,
    OnlineIndexRouter,
    PackOnlineIndex,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    async with create_pool() as pool:
        redis = create_redis()
        router = OnlineIndexRouter(
            pack=PackOnlineIndex(redis=redis),
            code=CodeOnlineIndex(redis=redis),
        )
        profiles = UserProfileRepository(pool=pool)
        try:
            await router.clear()
            rankable = [
                *await profiles.list_rankable(),
                *await profiles.list_online_code_users(),
            ]
            for profile in rankable:
                await router.sync(profile=profile)
            logger.info("online index backfill complete users=%d", len(rankable))
        finally:
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
