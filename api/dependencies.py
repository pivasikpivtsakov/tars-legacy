import asyncpg
from aiogram import Bot
from fastapi import Depends

from api.services.order_entity import OrderEntityService
from common.bot import create_bot
from common.db import create_pool
from common.environment import TELEGRAM_BOT_TOKEN
from common.repositories.orders import OrderRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.broadcast import BroadcastService
from common.services.external_order_api import ExternalOrderApi
from common.services.request_service import RequestService
from common.services.user_profiles import UserProfileService

bot = create_bot(token=TELEGRAM_BOT_TOKEN)

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await create_pool()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "database pool is not initialized"
    return _pool


def get_broadcast_service() -> BroadcastService:
    return BroadcastService(
        profiles=UserProfileRepository(pool=get_pool()),
    )


def get_user_profile_service() -> UserProfileService:
    return UserProfileService(
        repo=UserProfileRepository(pool=get_pool()),
    )


def get_request_service() -> RequestService:
    return RequestService()


def get_external_order_api(
    user_profile_service: UserProfileService = Depends(get_user_profile_service),
    requests: RequestService = Depends(get_request_service),
) -> ExternalOrderApi:
    return ExternalOrderApi(user_profiles=user_profile_service, requests=requests)


def get_order_entity_service(
    broadcast_service: BroadcastService = Depends(get_broadcast_service),
    external_api: ExternalOrderApi = Depends(get_external_order_api),
) -> OrderEntityService:
    return OrderEntityService(
        pool=get_pool(),
        bot=bot,
        broadcast=broadcast_service,
        orders=OrderRepository(pool=get_pool()),
        external_api=external_api,
    )


def get_bot() -> Bot:
    return bot
