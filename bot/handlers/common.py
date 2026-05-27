from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import BackCB, OpenZoneCB, StartZone, back_kb, welcome_kb
from bot.storage.user_profiles import UserProfile, UserProfileRepository

router = Router(name="start")


def _is_profile_complete(profile: UserProfile | None) -> bool:
    if profile is None:
        return False
    return (
        profile.works_alone is not None
        and profile.packages is not None
        and profile.work_start is not None
        and profile.work_end is not None
    )


def _welcome_kb(profile: UserProfile | None) -> InlineKeyboardMarkup:
    is_online = profile.is_online if profile is not None else False
    online_text = (
        _("start.btn_online_off") if is_online else _("start.btn_online_on")
    )
    return welcome_kb(
        online_text=online_text,
        withdraw_text=_("start.btn_withdraw"),
        packs_text=_("start.btn_packs"),
        priority_text=_("start.btn_priority"),
        register_text=_("start.btn_register"),
    )


async def render_welcome(
    *,
    target: Message | CallbackQuery,
    profile: UserProfile | None,
) -> None:
    text = _("start.welcome")
    kb = _welcome_kb(profile)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        return
    await target.answer(text, reply_markup=kb)


async def require_complete_profile(
    *,
    callback: CallbackQuery,
    profiles: UserProfileRepository,
) -> UserProfile | None:
    profile = await profiles.get(user_id=callback.from_user.id)
    if not _is_profile_complete(profile):
        await callback.answer(_("start.profile_required"), show_alert=True)
        return None
    return profile


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    await state.clear()
    profile = await profiles.get(user_id=message.from_user.id)
    await render_welcome(target=message, profile=profile)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.ONLINE))
async def open_online(
    callback: CallbackQuery,
    profiles: UserProfileRepository,
) -> None:
    if (await require_complete_profile(callback=callback, profiles=profiles)) is None:
        return
    profile = await profiles.toggle_is_online_and_get(user_id=callback.from_user.id)
    alert = (
        _("start.online_now_on") if profile.is_online else _("start.online_now_off")
    )
    await callback.answer(alert, show_alert=False)
    await render_welcome(target=callback, profile=profile)


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
    profiles: UserProfileRepository,
) -> None:
    await state.clear()
    profile = await profiles.get(user_id=callback.from_user.id)
    await render_welcome(target=callback, profile=profile)
    await callback.answer()
