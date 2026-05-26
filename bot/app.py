import asyncpg
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.i18n import FSMI18nMiddleware

from bot.handlers import admin, common, fallback, form
from bot.i18n import build_i18n
from bot.storage.postgres import PostgresStorage
from bot.storage.user_profiles import UserProfileRepository


def build_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    *,
    pool: asyncpg.Pool,
    admin_ids: frozenset[int],
) -> Dispatcher:
    dispatcher = Dispatcher(storage=PostgresStorage(pool=pool))
    dispatcher["profiles"] = UserProfileRepository(pool=pool)
    dispatcher["admin_ids"] = admin_ids
    dispatcher.update.middleware(FSMI18nMiddleware(i18n=build_i18n()))

    dispatcher.include_router(admin.router)
    dispatcher.include_router(common.router)
    dispatcher.include_router(form.router)
    dispatcher.include_router(fallback.router)

    return dispatcher
