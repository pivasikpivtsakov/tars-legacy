import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from common.db import create_pool
from common.environment import SCHEDULER_INTERVAL_SECONDS, TELEGRAM_BOT_TOKEN
from common.logging_config import setup_logging
from common.redis import create_redis
from scheduler.jobs.order_fanout import job__order_fanout

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()

    async with create_pool() as pool:
        redis = create_redis()
        bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        scheduler = AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1})
        scheduler.add_job(
            job__order_fanout,
            "interval",
            seconds=SCHEDULER_INTERVAL_SECONDS,
            kwargs={"bot": bot, "pool": pool, "redis": redis, "scheduler": scheduler},
            id="order_fanout",
        )

        logger.info("starting scheduler")
        scheduler.start()
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
            await bot.session.close()
            await redis.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
