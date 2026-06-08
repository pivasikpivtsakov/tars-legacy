import asyncpg
from aiogram import Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.i18n import FSMI18nMiddleware
from redis.asyncio import Redis

from bot.handlers import (
    admin,
    common,
    editing,
    fallback,
    menu,
    moderation,
    orders,
    registration,
    withdraw,
)
from bot.middlewares.profile import ProfileMiddleware
from common.environment import RATING_SPEED_WINDOW
from common.i18n import build_i18n
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import OrderLifecycle


def build_dispatcher(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    redis_url: str,
    admin_ids: frozenset[int],
    moderator_ids: frozenset[int],
) -> Dispatcher:
    storage = RedisStorage.from_url(
        redis_url,
        key_builder=DefaultKeyBuilder(prefix="aiogram_fsm", with_destiny=True),
    )
    dispatcher = Dispatcher(storage=storage)
    profiles = UserProfileRepository(pool=pool)
    orders_repo = OrderRepository(pool=pool)
    offers_repo = OrderOfferRepository(pool=pool)
    rating = RatingRepository(redis=redis, speed_window=RATING_SPEED_WINDOW)
    online_price_index = OnlinePriceIndex(redis=redis)
    pending = PendingOrdersRepository(redis=redis)
    dispatcher["profiles"] = profiles
    dispatcher["orders"] = orders_repo
    dispatcher["rating"] = rating
    dispatcher["online_price_index"] = online_price_index
    dispatcher["order_lifecycle"] = OrderLifecycle(
        pool=pool,
        orders=orders_repo,
        offers=offers_repo,
        profiles=profiles,
        rating=rating,
        pending=pending,
    )
    dispatcher["admin_ids"] = admin_ids
    dispatcher["moderator_ids"] = moderator_ids
    dispatcher.update.middleware(FSMI18nMiddleware(i18n=build_i18n()))

    profile_middleware = ProfileMiddleware(profiles=profiles)
    for router in (
        common.router,
        withdraw.router,
        editing.router,
        orders.router,
        menu.router,
    ):
        router.message.middleware(profile_middleware)
        router.callback_query.middleware(profile_middleware)

    dispatcher.include_router(admin.router)
    dispatcher.include_router(moderation.router)
    dispatcher.include_router(common.router)
    dispatcher.include_router(withdraw.router)
    dispatcher.include_router(orders.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(editing.router)
    dispatcher.include_router(menu.router)
    dispatcher.include_router(fallback.router)

    return dispatcher
