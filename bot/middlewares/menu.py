from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject, User
from aiogram.utils.i18n import gettext as _

from bot.forms.fields import begin_registration
from bot.forms.menu import build_menu_context, open_menu
from bot.forms.states import REGISTRATION_INPUT_STATES
from bot.keyboards.menu import MENU_BUTTON_KEY, reply_text_matches
from common.models.user_profiles import UserProfile
from common.repositories.user_profiles import UserProfileRepository

_MENU_COMMAND = "/menu"
_REGISTRATION_STATE_NAMES = frozenset(item.state for item in REGISTRATION_INPUT_STATES)


def _is_menu_command(text: str) -> bool:
    head = text.split(maxsplit=1)[0]
    return head.split("@", 1)[0] == _MENU_COMMAND


def is_menu_trigger(message: Message) -> bool:
    text = message.text
    if text is None:
        return False
    return _is_menu_command(text) or reply_text_matches(text, MENU_BUTTON_KEY)


class MenuMiddleware(BaseMiddleware):
    def __init__(self, *, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not is_menu_trigger(event):
            return await handler(event, data)
        state: FSMContext = data["state"]
        if data["raw_state"] in _REGISTRATION_STATE_NAMES:
            await event.answer(_("start.profile_required"))
            return None
        user: User = data["event_from_user"]
        profile: UserProfile | None = await self._profiles.get_by_tg_id(tg_id=user.id)
        moderator_ids: frozenset[int] = data["moderator_ids"]
        if profile is None:
            await begin_registration(message=event, state=state)
            return None
        context = await build_menu_context(
            target=event,
            state=state,
            profile=profile,
            admin_ids=data["admin_ids"],
            moderator_ids=moderator_ids,
            bot_switch=data["bot_switch"],
        )
        await open_menu(context)
        return None
