from collections.abc import Iterable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from bot.handlers.common import render_welcome, require_complete_profile
from bot.keyboards._packages import PackageToggleCB
from bot.keyboards.packs import PacksSaveCB, packages_editor_kb
from bot.keyboards.start import OpenZoneCB, StartZone
from bot.storage.user_profiles import UserProfileRepository

router = Router(name="packs")


class PacksEditor(StatesGroup):
    editing = State()


def _editor_kb(selected: Iterable[int]) -> InlineKeyboardMarkup:
    return packages_editor_kb(
        selected=selected,
        save_text=_("packs.btn_save"),
        back_text=_("start.btn_back"),
    )


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.PACKS))
async def open_packs(
    callback: CallbackQuery,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    profile = await require_complete_profile(callback=callback, profiles=profiles)
    if profile is None:
        return
    current = list(profile.packages) if profile.packages is not None else []
    await state.set_state(PacksEditor.editing)
    await state.update_data(packages=current)
    await callback.message.edit_text(
        _("packs.title"),
        reply_markup=_editor_kb(current),
    )
    await callback.answer()


@router.callback_query(PacksEditor.editing, PackageToggleCB.filter())
async def toggle_pack(
    callback: CallbackQuery,
    callback_data: PackageToggleCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    selected: set[int] = set(data["packages"])
    if callback_data.value in selected:
        selected.remove(callback_data.value)
    else:
        selected.add(callback_data.value)
    await state.update_data(packages=sorted(selected))
    await callback.message.edit_reply_markup(reply_markup=_editor_kb(selected))
    await callback.answer()


@router.callback_query(PacksEditor.editing, PacksSaveCB.filter())
async def save_packs(
    callback: CallbackQuery,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    data = await state.get_data()
    selected: list[int] = sorted(set(data["packages"]))
    if not selected:
        await callback.answer(
            _("registration.no_packages_selected"),
            show_alert=True,
        )
        return
    await profiles.set_packages(user_id=callback.from_user.id, packages=selected)
    await state.clear()
    profile = await profiles.get(user_id=callback.from_user.id)
    await render_welcome(target=callback, profile=profile)
    await callback.answer()
