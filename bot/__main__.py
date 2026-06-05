import asyncio
import logging

from bot.app import build_dispatcher
from common.bot import create_bot
from common.db import create_pool
from common.environment import (
    ADMIN_USER_IDS,
    MODERATOR_USER_IDS,
    REDIS_URL,
    TELEGRAM_BOT_TOKEN,
)
from common.logging_config import setup_logging
from common.redis import create_redis

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()

    async with create_pool() as pool:
        redis = create_redis()
        bot = create_bot(token=TELEGRAM_BOT_TOKEN)
        dispatcher = build_dispatcher(
            pool=pool,
            redis=redis,
            redis_url=REDIS_URL,
            admin_ids=ADMIN_USER_IDS,
            moderator_ids=MODERATOR_USER_IDS,
        )

        logger.info("starting bot polling")
        try:
            await dispatcher.start_polling(bot)
        finally:
            await bot.session.close()
            await dispatcher.storage.close()
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
