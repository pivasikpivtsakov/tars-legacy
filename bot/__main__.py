import asyncio
import logging
from urllib.parse import urlparse

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.app import build_dispatcher
from common.bot import create_bot
from common.db import create_pool
from common.environment import (
    REDIS_URL,
    TELEGRAM_BOT_TOKEN,
)
from common.logging_config import setup_logging
from common.redis import create_redis

logger = logging.getLogger(__name__)


def _build_scheduler() -> AsyncIOScheduler:
    parsed = urlparse(REDIS_URL)
    jobstore = RedisJobStore(
        db=int(parsed.path.lstrip("/") or 0),
        jobs_key="apscheduler:order_timeouts:jobs",
        run_times_key="apscheduler:order_timeouts:run_times",
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
    )
    return AsyncIOScheduler(jobstores={"default": jobstore})


async def main() -> None:
    setup_logging()

    async with create_pool() as pool:
        redis = create_redis()
        bot = create_bot(token=TELEGRAM_BOT_TOKEN)
        scheduler = _build_scheduler()
        dispatcher = build_dispatcher(
            pool=pool,
            redis=redis,
            redis_url=REDIS_URL,
            bot=bot,
            scheduler=scheduler,
        )
        scheduler.start()

        logger.info("starting bot polling")
        try:
            await dispatcher.start_polling(bot)
        finally:
            scheduler.shutdown(wait=False)
            await bot.session.close()
            await dispatcher.storage.close()
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
