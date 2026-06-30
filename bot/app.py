import asyncpg
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.i18n import FSMI18nMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
from common.environment import (
    LONG_RESERVE_CHAT_ID,
    ORDER_EXPIRY_DELAY_SECONDS,
    ORDER_EXPIRY_NOTIFICATION_1_DELAY_SECONDS,
    ORDER_EXPIRY_NOTIFICATION_2_DELAY_SECONDS,
    RATING_SPEED_WINDOW,
)
from common.i18n import build_i18n
from common.jobs.registry import set_job_services
from common.repositories.bot_switch import BotSwitchRepository
from common.repositories.online_index import (
    CodeOnlineIndex,
    OnlineIndexRouter,
    PackOnlineIndex,
)
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pack_price_limits import PackPriceLimitRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.rating import RatingRepository
from common.repositories.transactions import TransactionsRepository
from common.repositories.user_profiles import UserProfileRepository
from common.repositories.user_roles import UserRoleRepository
from common.services.anti_fraud import AntiFraudService
from common.services.bot_switch import BotSwitchService
from common.services.broadcast import BroadcastService
from common.services.dispatch_signal import DispatchSignal
from common.services.external_order_api import ExternalOrderApi
from common.services.moderation import ModerationService
from common.services.order_processing import OrderLifecycle
from common.services.order_timeouts import OrderTimeoutService
from common.services.ranking import build_strategies
from common.services.request_service import RequestService
from common.services.user_profiles import UserProfileService


def build_dispatcher(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    redis_url: str,
    bot: Bot,
    scheduler: AsyncIOScheduler,
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
    online_price_index = OnlineIndexRouter(
        pack=PackOnlineIndex(redis=redis),
        code=CodeOnlineIndex(redis=redis),
    )
    transactions = TransactionsRepository(pool=pool)
    strategies = build_strategies(
        online_index=online_price_index,
        rating=rating,
        transactions=transactions,
    )
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
    dispatcher["transactions"] = transactions
    dispatcher["pack_price_limits"] = PackPriceLimitRepository(redis=redis)
    dispatcher["dispatch_signal"] = dispatch_signal
    order_lifecycle = OrderLifecycle(
        pool=pool,
        orders=orders_repo,
        offers=offers_repo,
        profiles=profiles,
        rating=rating,
        pending=pending,
        dispatch_signal=dispatch_signal,
        strategies=strategies,
        bot=bot,
        long_reserve_chat_id=LONG_RESERVE_CHAT_ID,
    )
    dispatcher["order_lifecycle"] = order_lifecycle
    order_timeouts = OrderTimeoutService(
        scheduler=scheduler,
        bot=bot,
        redis=redis,
        orders=orders_repo,
        lifecycle=order_lifecycle,
        notification_1_delay=ORDER_EXPIRY_NOTIFICATION_1_DELAY_SECONDS,
        notification_2_delay=ORDER_EXPIRY_NOTIFICATION_2_DELAY_SECONDS,
        expiry_delay=ORDER_EXPIRY_DELAY_SECONDS,
    )
    dispatcher["order_timeouts"] = order_timeouts
    set_job_services(order_timeouts=order_timeouts)
    dispatcher["anti_fraud"] = AntiFraudService(
        orders=orders_repo,
        external_api=external_order_api,
        user_profiles=UserProfileService(repo=profiles),
    )
    dispatcher["roles"] = roles
    dispatcher["bot_switch"] = bot_switch
    dispatcher["broadcast"] = broadcast
    dispatcher["moderation"] = ModerationService(
        profiles=profiles,
        online_price_index=online_price_index,
    )
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
