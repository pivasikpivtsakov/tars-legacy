from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from aiogram import BaseMiddleware, flags
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from aiogram.utils.i18n import gettext as _

from common.models.user_profiles import UserProfile, UserProfileStatus
from common.repositories.user_profiles import UserProfileRepository

PROFILE_REQUIREMENT_FLAG = "profile_requirement"


class ProfileRequirement(StrEnum):
    COMPLETE = "complete"
    ACTIVE = "active"


require_complete_profile = flags.profile_requirement(ProfileRequirement.COMPLETE)
require_active_profile = flags.profile_requirement(ProfileRequirement.ACTIVE)


def _is_profile_complete(profile: UserProfile | None) -> bool:
    if profile is None:
        return False
    return (
        profile.chat_addable is not None
        and bool(profile.prices)
        and profile.withdrawal_method is not None
        and profile.work_start is not None
        and profile.work_end is not None
    )


def _requirement_alert(
    requirement: ProfileRequirement,
    profile: UserProfile | None,
) -> str | None:
    if not _is_profile_complete(profile):
        return _("start.profile_required")
    if requirement is ProfileRequirement.ACTIVE and profile.status is not UserProfileStatus.ACTIVE:
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
        requirement = get_flag(data, PROFILE_REQUIREMENT_FLAG)
        if requirement is not None:
            alert = _requirement_alert(requirement, profile)
            if alert is not None:
                await _reject(event, alert)
                return None
        return await handler(event, data)
