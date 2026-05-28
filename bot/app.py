from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import TelegramObject, User
from aiogram.utils.i18n import FSMI18nMiddleware

from bot.handlers import admin, common, fallback, packs, registration, withdraw
from bot.i18n import build_i18n
from bot.storage.user_profiles import UserProfileRepository


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


def build_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    *,
    pool: asyncpg.Pool,
    redis_url: str,
    admin_ids: frozenset[int],
) -> Dispatcher:
    storage = RedisStorage.from_url(
        redis_url,
        key_builder=DefaultKeyBuilder(prefix="aiogram_fsm", with_destiny=True),
    )
    dispatcher = Dispatcher(storage=storage)
    dispatcher["profiles"] = UserProfileRepository(pool=pool)
    dispatcher["admin_ids"] = admin_ids
    dispatcher.update.middleware(FSMI18nMiddleware(i18n=build_i18n()))

    profile_middleware = _ProfileMiddleware()
    for router in (common.router, withdraw.router, packs.router):
        router.message.middleware(profile_middleware)
        router.callback_query.middleware(profile_middleware)

    dispatcher.include_router(admin.router)
    dispatcher.include_router(common.router)
    dispatcher.include_router(withdraw.router)
    dispatcher.include_router(packs.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(fallback.router)

    return dispatcher
