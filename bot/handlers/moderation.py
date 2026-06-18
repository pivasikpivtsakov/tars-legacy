import contextlib

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import CallbackQuery, User
from aiogram.utils.i18n import gettext as _

from bot.forms.menu import send_menu
from common.keyboards.moderation import (
    ModApproveCB,
    ModDenyCB,
    ModEditPacksCB,
    ModPacksCancelCB,
    ModPacksSaveCB,
    ModPackToggleCB,
    ModToggleCodesCB,
    mask_to_packages,
    moderation_decision_kb,
    moderation_packages_kb,
    packages_to_mask,
)
from common.models.user_profiles import UserProfile
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import is_moderator

router = Router(name="moderation")


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


@router.callback_query(ModToggleCodesCB.filter(), _is_moderator)
async def toggle_with_codes(
    callback: CallbackQuery,
    callback_data: ModToggleCodesCB,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=moderation_decision_kb(
            profile_id=callback_data.profile_id,
            with_codes=not callback_data.with_codes,
        ),
    )
    await callback.answer()


@router.callback_query(ModEditPacksCB.filter(), _is_moderator)
async def open_pack_editor(
    callback: CallbackQuery,
    callback_data: ModEditPacksCB,
    profiles: UserProfileRepository,
) -> None:
    profile = await profiles.get_by_id(profile_id=callback_data.profile_id)
    if profile is None:
        await callback.answer(_("moderation.profile_not_found"), show_alert=True)
        return
    await callback.message.edit_reply_markup(
        reply_markup=moderation_packages_kb(
            profile_id=callback_data.profile_id,
            with_codes=callback_data.with_codes,
            mask=packages_to_mask(profile.packages or ()),
        ),
    )
    await callback.answer()


@router.callback_query(ModPackToggleCB.filter(), _is_moderator)
async def toggle_pack(
    callback: CallbackQuery,
    callback_data: ModPackToggleCB,
) -> None:
    new_mask = callback_data.mask ^ (1 << callback_data.idx)
    await callback.message.edit_reply_markup(
        reply_markup=moderation_packages_kb(
            profile_id=callback_data.profile_id,
            with_codes=callback_data.with_codes,
            mask=new_mask,
        ),
    )
    await callback.answer()


@router.callback_query(ModPacksSaveCB.filter(), _is_moderator)
async def save_packs(
    callback: CallbackQuery,
    callback_data: ModPacksSaveCB,
    profiles: UserProfileRepository,
) -> None:
    if callback_data.mask == 0:
        await callback.answer(_("moderation.no_packages_selected"), show_alert=True)
        return
    try:
        await profiles.set_packages(
            profile_id=callback_data.profile_id,
            packages=mask_to_packages(callback_data.mask),
        )
    except LookupError:
        await callback.answer(_("moderation.profile_not_found"), show_alert=True)
        return
    await callback.message.edit_reply_markup(
        reply_markup=moderation_decision_kb(
            profile_id=callback_data.profile_id,
            with_codes=callback_data.with_codes,
        ),
    )
    await callback.answer(_("moderation.packages_saved"))


@router.callback_query(ModPacksCancelCB.filter(), _is_moderator)
async def cancel_packs(
    callback: CallbackQuery,
    callback_data: ModPacksCancelCB,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=moderation_decision_kb(
            profile_id=callback_data.profile_id,
            with_codes=callback_data.with_codes,
        ),
    )
    await callback.answer()


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
            with_codes=callback_data.with_codes,
        )
    except LookupError:
        await callback.answer(_("moderation.profile_not_found"), show_alert=True)
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
