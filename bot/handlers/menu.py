from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import welcome_kb
from common.repositories.user_profiles import UserProfile


def _is_profile_complete(profile: UserProfile | None) -> bool:
    if profile is None:
        return False
    return (
        profile.works_alone is not None
        and profile.packages is not None
        and profile.price_60 is not None
        and profile.work_start is not None
        and profile.work_end is not None
    )


def _menu_kb(profile: UserProfile | None) -> InlineKeyboardMarkup:
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


async def render_menu(
    *,
    target: Message | CallbackQuery,
    profile: UserProfile | None,
) -> None:
    text = _("start.welcome")
    kb = _menu_kb(profile)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        return
    await target.answer(text, reply_markup=kb)


async def require_complete_profile(
    *,
    callback: CallbackQuery,
    profile: UserProfile | None,
) -> UserProfile | None:
    if not _is_profile_complete(profile):
        await callback.answer(_("start.profile_required"), show_alert=True)
        return None
    return profile
