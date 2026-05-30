import asyncio
from datetime import datetime
import logging

import asyncpg
from aiogram import Bot

from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_fanout import offer_order_to_next_user
from common.services.order_processing import OrderManager

logger = logging.getLogger(__name__)


async def fan_out_active_orders(
    *,
    bot: Bot,
    orders: OrderRepository,
    offers: OrderOfferRepository,
    order_manager: OrderManager,
) -> None:
    active_orders = await orders.list_active_for_fanout()
    await asyncio.gather(
        *(
            offer_order_to_next_user(
                order=order,
                bot=bot,
                orders=orders,
                offers=offers,
                order_manager=order_manager,
            )
            for order in active_orders
        ),
    )


async def job__order_fanout(*, bot: Bot, pool: asyncpg.Pool) -> None:
    start_time = datetime.now()
    logger.info(f"order fanout started timestamp={start_time}")

    orders = OrderRepository(pool=pool)
    offers = OrderOfferRepository(pool=pool)
    order_manager = OrderManager(profiles=UserProfileRepository(pool=pool))

    await fan_out_active_orders(
        bot=bot,
        orders=orders,
        offers=offers,
        order_manager=order_manager,
    )

    end_time = datetime.now()
    elapsed_time = end_time - start_time
    logger.info(f"order fanout completed timestamp={end_time} elapsed_time={elapsed_time}")
