import contextlib

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import CallbackQuery, User
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import send_menu
from common.keyboards.moderation import ModApproveCB, ModDenyCB
from common.models.user_profiles import UserProfile
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


async def _notify_approved(
    *,
    bot: Bot,
    profile: UserProfile,
    state: FSMContext,
) -> None:
    with contextlib.suppress(TelegramAPIError):
        await bot.send_message(chat_id=profile.tg_id, text=_("start.approved"))
        await send_menu(
            bot=bot,
            chat_id=profile.tg_id,
            state=state,
            profile=profile,
        )


def _user_state(*, storage: BaseStorage, bot: Bot, tg_id: int) -> FSMContext:
    key = StorageKey(bot_id=bot.id, chat_id=tg_id, user_id=tg_id)
    return FSMContext(storage=storage, key=key)


@router.callback_query(ModApproveCB.filter(), _is_moderator)
async def approve_user(
    callback: CallbackQuery,
    callback_data: ModApproveCB,
    bot: Bot,
    profiles: UserProfileRepository,
    fsm_storage: BaseStorage,
) -> None:
    try:
        profile = await profiles.approve(
            profile_id=callback_data.profile_id,
            with_codes=False,
        )
    except LookupError:
        await callback.answer("user not found", show_alert=True)
        return
    user_state = _user_state(storage=fsm_storage, bot=bot, tg_id=profile.tg_id)
    await user_state.clear()
    await _annotate(
        callback=callback,
        note=f"#approved by {_moderator_label(callback.from_user)}",
    )
    await callback.answer()
    await _notify_approved(bot=bot, profile=profile, state=user_state)


@router.callback_query(ModDenyCB.filter(), _is_moderator)
async def deny_user(callback: CallbackQuery) -> None:
    await _annotate(
        callback=callback,
        note=f"#denied by {_moderator_label(callback.from_user)}",
    )
    await callback.answer()
