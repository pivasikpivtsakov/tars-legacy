from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
from aiogram import BaseMiddleware, Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import TelegramObject, User
from aiogram.utils.i18n import FSMI18nMiddleware
from redis.asyncio import Redis

from bot.handlers import admin, common, fallback, orders, packs, registration, withdraw
from common.environment import RATING_SPEED_WINDOW
from common.i18n import build_i18n
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import OrderLifecycle, OrderManager


class _ProfileMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User = data["event_from_user"]
        profiles: UserProfileRepository = data["profiles"]
        data["profile"] = await profiles.get(user_id=user.id)
        return await handler(event, data)


def build_dispatcher(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    redis_url: str,
    admin_ids: frozenset[int],
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
    dispatcher["profiles"] = profiles
    dispatcher["orders"] = orders_repo
    dispatcher["rating"] = rating
    dispatcher["order_manager"] = OrderManager(profiles=profiles, rating=rating)
    dispatcher["order_lifecycle"] = OrderLifecycle(
        pool=pool,
        orders=orders_repo,
        offers=offers_repo,
        profiles=profiles,
        rating=rating,
    )
    dispatcher["admin_ids"] = admin_ids
    dispatcher.update.middleware(FSMI18nMiddleware(i18n=build_i18n()))

    profile_middleware = _ProfileMiddleware()
    for router in (common.router, withdraw.router, packs.router, orders.router):
        router.message.middleware(profile_middleware)
        router.callback_query.middleware(profile_middleware)

    dispatcher.include_router(admin.router)
    dispatcher.include_router(common.router)
    dispatcher.include_router(withdraw.router)
    dispatcher.include_router(packs.router)
    dispatcher.include_router(orders.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(fallback.router)

    return dispatcher
