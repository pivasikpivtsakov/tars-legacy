from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, flags
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from aiogram.utils.i18n import gettext as _

from common.models.user_profiles import UserProfile, UserProfileStatus
from common.repositories.postgres.user_profiles import UserProfileRepository

REQUIRE_ACTIVE_PROFILE_FLAG = "require_active_profile"

require_active_profile = flags.require_active_profile


def _active_gate_alert(profile: UserProfile | None) -> str | None:
    if profile is None:
        return _("start.profile_required")
    if profile.status is not UserProfileStatus.ACTIVE:
        return _("start.action_needs_active")
    return None


async def _reject(event: TelegramObject, text: str) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    elif isinstance(event, Message):
        await event.answer(text)


class ProfileMiddleware(BaseMiddleware):
    def __init__(self, *, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User = data["event_from_user"]
        profile = await self._profiles.get_by_tg_id(tg_id=user.id)
        data["profile"] = profile
        if get_flag(data, REQUIRE_ACTIVE_PROFILE_FLAG):
            alert = _active_gate_alert(profile)
            if alert is not None:
                await _reject(event, alert)
                return None
        return await handler(event, data)
