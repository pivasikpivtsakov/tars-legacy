import logging
import time

import asyncpg
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from common.environment import RATING_SPEED_WINDOW
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_fanout import fan_out_active_orders
from common.services.order_processing import OrderManager

logger = logging.getLogger(__name__)


async def job__order_fanout(
    *,
    bot: Bot,
    pool: asyncpg.Pool,
    redis: Redis,
    scheduler: AsyncIOScheduler,
) -> None:
    started = time.perf_counter()
    logger.info("order fanout started")

    orders = OrderRepository(pool=pool)
    offers = OrderOfferRepository(pool=pool)
    rating = RatingRepository(redis=redis, speed_window=RATING_SPEED_WINDOW)
    order_manager = OrderManager(
        profiles=UserProfileRepository(pool=pool),
        rating=rating,
    )

    await fan_out_active_orders(
        bot=bot,
        orders=orders,
        offers=offers,
        order_manager=order_manager,
        rating=rating,
        scheduler=scheduler,
    )

    logger.info("order fanout completed elapsed=%.3fs", time.perf_counter() - started)
