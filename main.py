import asyncio
import logging

from bot.app import build_bot, build_dispatcher
from bot.db import create_pool
from bot.logging_config import setup_logging
from environment import ADMIN_USER_IDS, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()

    pool = await create_pool()
    bot = build_bot(token=TELEGRAM_BOT_TOKEN)
    dispatcher = build_dispatcher(pool=pool, admin_ids=ADMIN_USER_IDS)

    logger.info("starting bot polling")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
