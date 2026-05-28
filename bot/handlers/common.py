from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import render_menu, require_complete_profile
from bot.handlers.registration import begin_registration
from bot.keyboards.start import BackCB, OpenZoneCB, StartZone, back_kb
from common.repositories.user_profiles import UserProfile, UserProfileRepository

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await state.clear()
    if profile is None:
        await begin_registration(message=message, state=state)
        return
    await render_menu(target=message, profile=profile)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.ONLINE))
async def open_online(
    callback: CallbackQuery,
    profiles: UserProfileRepository,
    profile: UserProfile | None,
) -> None:
    if (await require_complete_profile(callback=callback, profile=profile)) is None:
        return
    profile = await profiles.toggle_is_online_and_get(user_id=callback.from_user.id)
    alert = (
        _("start.online_now_on") if profile.is_online else _("start.online_now_off")
    )
    await callback.answer(alert, show_alert=False)
    await render_menu(target=callback, profile=profile)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.PRIORITY))
async def open_priority(callback: CallbackQuery) -> None:
    text = _("start.priority").format(speed=0, price=0, cancellations=0)
    await callback.message.edit_text(
        text,
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()


@router.callback_query(BackCB.filter())
async def back_to_welcome(
    callback: CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await state.clear()
    await render_menu(target=callback, profile=profile)
    await callback.answer()
