from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User
from aiogram.utils.i18n import gettext as _

from common.repositories.user_profiles import UserProfileRepository
from common.services.bot_switch import BotSwitchService


class BotSwitchMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        switch: BotSwitchService,
        profiles: UserProfileRepository,
    ) -> None:
        self._switch = switch
        self._profiles = profiles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if await self._switch.is_enabled():
            return await handler(event, data)
        if await self._is_admin(data=data):
            return await handler(event, data)
        if isinstance(event, Update):
            await _answer_disabled(event)
        return None

    async def _is_admin(self, *, data: dict[str, Any]) -> bool:
        admin_ids: frozenset[int] = data["admin_ids"]
        user: User | None = data.get("event_from_user")
        if user is None or not admin_ids:
            return False
        profile = await self._profiles.get_by_tg_id(tg_id=user.id)
        return profile is not None and profile.id in admin_ids


async def _answer_disabled(update: Update) -> None:
    text = _("service.disabled")
    message = update.message or update.edited_message
    if message is not None:
        await message.answer(text)
        return
    if update.callback_query is not None:
        await update.callback_query.answer(text, show_alert=True)
