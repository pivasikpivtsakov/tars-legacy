import logging

from common.environment import SCHEDULER_INTERVAL_SECONDS
from scheduler.app import sched

logger = logging.getLogger(__name__)


@sched.scheduled_job(
    "interval",
    seconds=SCHEDULER_INTERVAL_SECONDS,
    id="order_fanout",
)
async def order_fanout() -> None:
    logger.info("order_fanout")
