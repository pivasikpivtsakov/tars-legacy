import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, User

from common.keyboards.moderation import ModApproveCB, ModDenyCB
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import is_moderator

router = Router(name="moderation")

MODERATOR_PANEL_TEXT = (
    "You are a moderator.\n"
    "You will receive approval requests when users register or update their "
    "registration data. Use the buttons on each request to approve or deny."
)
MODERATOR_NOT_ORDER_TAKER = "Moderators cannot register as order-takers."


class _IsModerator(BaseFilter):
    async def __call__(
        self,
        callback: CallbackQuery,
        moderator_ids: frozenset[int],
        profiles: UserProfileRepository,
    ) -> bool:
        user = callback.from_user
        if user is None:
            return False
        return await is_moderator(
            profiles=profiles,
            moderator_ids=moderator_ids,
            tg_id=user.id,
        )


_is_moderator = _IsModerator()


def _moderator_label(user: User) -> str:
    return f"@{user.username}" if user.username else f"id={user.id}"


async def _annotate(*, callback: CallbackQuery, note: str) -> None:
    base = callback.message.text or ""
    text = f"{base}\n\n{note}" if base else note
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None)


@router.callback_query(ModApproveCB.filter(), _is_moderator)
async def approve_user(
    callback: CallbackQuery,
    callback_data: ModApproveCB,
    profiles: UserProfileRepository,
) -> None:
    try:
        await profiles.approve(profile_id=callback_data.profile_id, with_codes=False)
    except LookupError:
        await callback.answer("user not found", show_alert=True)
        return
    await _annotate(
        callback=callback,
        note=f"#approved by {_moderator_label(callback.from_user)}",
    )
    await callback.answer()


@router.callback_query(ModDenyCB.filter(), _is_moderator)
async def deny_user(callback: CallbackQuery) -> None:
    await _annotate(
        callback=callback,
        note=f"#denied by {_moderator_label(callback.from_user)}",
    )
    await callback.answer()
