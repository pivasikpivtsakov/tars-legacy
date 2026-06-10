from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User
from aiogram.utils.i18n import gettext as _

from common.services.bot_switch import BotSwitchService


class BotSwitchMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        switch: BotSwitchService,
        admin_ids: frozenset[int],
    ) -> None:
        self._switch = switch
        self._admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None and user.id in self._admin_ids:
            return await handler(event, data)
        if await self._switch.is_enabled():
            return await handler(event, data)
        if isinstance(event, Update):
            await _answer_disabled(event)
        return None


async def _answer_disabled(update: Update) -> None:
    text = _("service.disabled")
    message = update.message or update.edited_message
    if message is not None:
        await message.answer(text)
        return
    if update.callback_query is not None:
        await update.callback_query.answer(text, show_alert=True)
