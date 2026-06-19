from typing import Annotated

import asyncpg
from aiogram import Bot
from fastapi import Depends
from redis.asyncio import Redis

from api.services.order_entity import OrderEntityService
from common.bot import create_bot
from common.db import create_pool
from common.environment import TELEGRAM_BOT_TOKEN
from common.redis import create_redis
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.broadcast import BroadcastService
from common.services.external_order_api import ExternalOrderApi
from common.services.request_service import RequestService

bot = create_bot(token=TELEGRAM_BOT_TOKEN)


class _Connections:
    pool: asyncpg.Pool | None = None
    redis: Redis | None = None


async def init_pool() -> asyncpg.Pool:
    if _Connections.pool is None:
        _Connections.pool = await create_pool()
    return _Connections.pool


async def close_pool() -> None:
    if _Connections.pool is not None:
        await _Connections.pool.close()
        _Connections.pool = None


def get_pool() -> asyncpg.Pool:
    assert _Connections.pool is not None, "database pool is not initialized"
    return _Connections.pool


def init_redis() -> Redis:
    if _Connections.redis is None:
        _Connections.redis = create_redis()
    return _Connections.redis


async def close_redis() -> None:
    if _Connections.redis is not None:
        await _Connections.redis.aclose()
        _Connections.redis = None


def get_redis() -> Redis:
    assert _Connections.redis is not None, "redis client is not initialized"
    return _Connections.redis


def get_broadcast_service() -> BroadcastService:
    return BroadcastService(
        profiles=UserProfileRepository(pool=get_pool()),
    )


def get_request_service() -> RequestService:
    return RequestService()


def get_external_order_api(
    requests: Annotated[RequestService, Depends(get_request_service)],
) -> ExternalOrderApi:
    return ExternalOrderApi(requests=requests)


def get_order_entity_service(
    broadcast_service: Annotated[BroadcastService, Depends(get_broadcast_service)],
    external_api: Annotated[ExternalOrderApi, Depends(get_external_order_api)],
) -> OrderEntityService:
    return OrderEntityService(
        pool=get_pool(),
        bot=bot,
        broadcast=broadcast_service,
        orders=OrderRepository(pool=get_pool()),
        offers=OrderOfferRepository(pool=get_pool()),
        pending=PendingOrdersRepository(redis=get_redis()),
        external_api=external_api,
    )


def get_bot() -> Bot:
    return bot
