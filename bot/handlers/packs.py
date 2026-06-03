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
from common.models.user_profiles import UserProfile
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository

router = Router(name="packs")


class PacksEditor(StatesGroup):
    editing = State()


def _editor_kb(selected: Iterable[int]) -> InlineKeyboardMarkup:
    return packages_editor_kb(
        selected=selected,
        back_text=_("start.btn_back"),
    )


def selected_packages(profile: UserProfile | None) -> set[int]:
    if profile is None or profile.packages is None:
        return set()
    return set(profile.packages)


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
    online_price_index: OnlinePriceIndex,
    profile: UserProfile | None,
) -> None:
    complete_profile = await require_complete_profile(callback=callback, profile=profile)
    if complete_profile is None:
        return
    selected = selected_packages(complete_profile)
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
    updated = await profiles.set_packages(
        profile_id=complete_profile.id,
        packages=sorted(selected),
    )
    await online_price_index.sync(profile=updated)
    await callback.message.edit_reply_markup(reply_markup=_editor_kb(selected))
    await callback.answer()
