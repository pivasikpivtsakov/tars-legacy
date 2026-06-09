import asyncio
import contextlib
import logging
from functools import partial

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis import ConnectionPool

from common.bot import create_bot
from common.db import create_pool
from common.environment import (
    MODERATOR_USER_IDS,
    REDIS_JOBSTORE_KEY_PREFIX,
    REDIS_URL,
    SCHEDULER_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
)
from common.logging_config import setup_logging
from common.redis import create_redis
from common.services.dispatch_signal import DispatchSignal
from common.services.order_fanout import init_fanout_context
from scheduler.dispatch import DispatchRunner
from scheduler.jobs.offer_expiry import schedule_offer_expiry
from scheduler.jobs.order_fanout import dispatch_once, job__order_fanout

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()

    async with create_pool() as pool:
        redis = create_redis()
        bot = create_bot(token=TELEGRAM_BOT_TOKEN)
        jobstores = {
            "default": RedisJobStore(
                jobs_key=f"{REDIS_JOBSTORE_KEY_PREFIX}:jobs",
                run_times_key=f"{REDIS_JOBSTORE_KEY_PREFIX}:run_times",
                connection_pool=ConnectionPool.from_url(REDIS_URL),
            ),
        }
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        runner = DispatchRunner(run=dispatch_once)
        init_fanout_context(
            pool=pool,
            redis=redis,
            bot=bot,
            schedule_expiry=partial(schedule_offer_expiry, scheduler=scheduler),
            request_dispatch=runner.request,
            excluded_user_ids=MODERATOR_USER_IDS,
        )
        scheduler.add_job(
            job__order_fanout,
            "interval",
            seconds=SCHEDULER_INTERVAL_SECONDS,
            id="order_fanout",
            replace_existing=True,
            misfire_grace_time=SCHEDULER_INTERVAL_SECONDS,
        )

        signal = DispatchSignal(redis=redis)
        listener = asyncio.create_task(signal.listen(on_wake=runner.request))

        logger.info("starting scheduler")
        runner.start()
        runner.request()  # drain any backlog left from downtime immediately
        scheduler.start()
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener
            await runner.stop()
            await bot.session.close()
            await redis.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
