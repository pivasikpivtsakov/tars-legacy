import asyncio
import contextlib
import logging

import scheduler.jobs  # noqa: F401  decoration side-effect registers jobs on `sched`
from common.logging_config import setup_logging
from scheduler.app import sched

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()

    logger.info("starting scheduler")
    sched.start()
    try:
        await asyncio.Event().wait()
    finally:
        sched.shutdown(wait=False)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
