from apscheduler.schedulers.asyncio import AsyncIOScheduler

sched: AsyncIOScheduler = AsyncIOScheduler(
    job_defaults={"coalesce": True, "max_instances": 1},
)
