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
    moderation,
    orders,
    pack_limits,
    packages,
    registration,
    withdraw,
)
from bot.middlewares.bot_switch import BotSwitchMiddleware
from bot.middlewares.logging import LoggingContextMiddleware
from bot.middlewares.menu import MenuMiddleware
from bot.middlewares.profile import ProfileMiddleware
from bot.middlewares.roles import RoleContextMiddleware
from common.environment import RATING_SPEED_WINDOW
from common.i18n import build_i18n
from common.repositories.bot_switch import BotSwitchRepository
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pack_price_limits import PackPriceLimitRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.repositories.user_roles import UserRoleRepository
from common.services.anti_fraud import AntiFraudService
from common.services.bot_switch import BotSwitchService
from common.services.broadcast import BroadcastService
from common.services.dispatch_signal import DispatchSignal
from common.services.external_order_api import ExternalOrderApi
from common.services.order_processing import OrderLifecycle
from common.services.request_service import RequestService
from common.services.user_profiles import UserProfileService


def build_dispatcher(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    redis_url: str,
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
    dispatch_signal = DispatchSignal(redis=redis)
    bot_switch_repo = BotSwitchRepository(redis=redis)
    roles = UserRoleRepository(redis=redis)
    bot_switch = BotSwitchService(
        repo=bot_switch_repo,
        profiles=profiles,
        online_price_index=online_price_index,
    )
    broadcast = BroadcastService(profiles=profiles)
    external_order_api = ExternalOrderApi(requests=RequestService())
    dispatcher["profiles"] = profiles
    dispatcher["rating"] = rating
    dispatcher["online_price_index"] = online_price_index
    dispatcher["pack_price_limits"] = PackPriceLimitRepository(redis=redis)
    dispatcher["dispatch_signal"] = dispatch_signal
    dispatcher["order_lifecycle"] = OrderLifecycle(
        pool=pool,
        orders=orders_repo,
        offers=offers_repo,
        profiles=profiles,
        rating=rating,
        pending=pending,
        dispatch_signal=dispatch_signal,
    )
    dispatcher["anti_fraud"] = AntiFraudService(
        orders=orders_repo,
        external_api=external_order_api,
        user_profiles=UserProfileService(repo=profiles),
    )
    dispatcher["roles"] = roles
    dispatcher["bot_switch"] = bot_switch
    dispatcher["broadcast"] = broadcast
    dispatcher.update.outer_middleware(LoggingContextMiddleware())
    dispatcher.update.outer_middleware(RoleContextMiddleware(roles=roles))
    dispatcher.update.middleware(FSMI18nMiddleware(i18n=build_i18n()))
    dispatcher.update.middleware(
        BotSwitchMiddleware(switch=bot_switch, profiles=profiles),
    )
    dispatcher.message.outer_middleware(MenuMiddleware(profiles=profiles))

    profile_middleware = ProfileMiddleware(profiles=profiles)
    for router in (
        common.router,
        withdraw.router,
        editing.router,
        orders.router,
    ):
        router.message.middleware(profile_middleware)
        router.callback_query.middleware(profile_middleware)

    dispatcher.include_router(admin.router)
    dispatcher.include_router(moderation.router)
    dispatcher.include_router(pack_limits.router)
    dispatcher.include_router(common.router)
    dispatcher.include_router(withdraw.router)
    dispatcher.include_router(orders.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(editing.router)
    dispatcher.include_router(packages.router)
    dispatcher.include_router(fallback.router)

    return dispatcher
