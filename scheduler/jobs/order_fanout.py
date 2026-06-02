import asyncio
import logging
from datetime import datetime

import asyncpg
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from common.environment import RATING_SPEED_WINDOW
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import OrderManager
from scheduler.services.order_fanout import offer_order_to_next_user

logger = logging.getLogger(__name__)


async def fan_out_active_orders(
    *,
    bot: Bot,
    orders: OrderRepository,
    offers: OrderOfferRepository,
    order_manager: OrderManager,
    rating: RatingRepository,
    scheduler: AsyncIOScheduler,
) -> None:
    active_orders = await orders.list_active_for_fanout()
    # todo: разбить на чанки итд?
    await asyncio.gather(
        *(
            offer_order_to_next_user(
                order=order,
                bot=bot,
                orders=orders,
                offers=offers,
                order_manager=order_manager,
                rating=rating,
                scheduler=scheduler,
            )
            for order in active_orders
        ),
    )


async def job__order_fanout(
    *,
    bot: Bot,
    pool: asyncpg.Pool,
    redis: Redis,
    scheduler: AsyncIOScheduler,
) -> None:
    start_time = datetime.now()
    logger.info(f"order fanout started timestamp={start_time}")

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

    end_time = datetime.now()
    elapsed_time = end_time - start_time
    logger.info(f"order fanout completed timestamp={end_time} elapsed_time={elapsed_time}")
