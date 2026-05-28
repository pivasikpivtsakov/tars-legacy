from collections.abc import Iterable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import require_complete_profile
from bot.keyboards._packages import PackageToggleCB
from bot.keyboards.packs import packages_editor_kb
from bot.keyboards.start import OpenZoneCB, StartZone
from bot.storage.user_profiles import (
    UserProfile,
    UserProfileRepository,
    selected_packages,
)

router = Router(name="packs")


class PacksEditor(StatesGroup):
    editing = State()


def _editor_kb(selected: Iterable[int]) -> InlineKeyboardMarkup:
    return packages_editor_kb(
        selected=selected,
        back_text=_("start.btn_back"),
    )


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.PACKS))
async def open_packs(
    callback: CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    if (await require_complete_profile(callback=callback, profile=profile)) is None:
        return
    await state.set_state(PacksEditor.editing)
    await callback.message.edit_text(
        _("packs.title"),
        reply_markup=_editor_kb(selected_packages(profile)),
    )
    await callback.answer()


@router.callback_query(PacksEditor.editing, PackageToggleCB.filter())
async def toggle_pack(
    callback: CallbackQuery,
    callback_data: PackageToggleCB,
    profiles: UserProfileRepository,
    profile: UserProfile | None,
) -> None:
    selected = selected_packages(profile)
    if callback_data.value in selected:
        if len(selected) == 1:
            await callback.answer(
                _("registration.no_packages_selected"),
                show_alert=True,
            )
            return
        selected.remove(callback_data.value)
    else:
        selected.add(callback_data.value)
    await profiles.set_packages(
        user_id=callback.from_user.id,
        packages=sorted(selected),
    )
    await callback.message.edit_reply_markup(reply_markup=_editor_kb(selected))
    await callback.answer()
