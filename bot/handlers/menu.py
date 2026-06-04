from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import StartZone, back_kb, welcome_kb
from common.models.user_profiles import UserProfile, UserProfileStatus


def _full_menu_kb(profile: UserProfile) -> InlineKeyboardMarkup:
    online_text = (
        _("start.btn_online_off") if profile.is_online else _("start.btn_online_on")
    )
    return welcome_kb(
        buttons={
            StartZone.ONLINE: online_text,
            StartZone.BALANCE: _("start.btn_balance"),
            StartZone.WITHDRAW: _("start.btn_withdraw"),
            StartZone.PACKS: _("start.btn_packs"),
            StartZone.PRIORITY: _("start.btn_priority"),
            StartZone.REGISTER: _("start.btn_register"),
        },
    )


def _register_only_kb() -> InlineKeyboardMarkup:
    return welcome_kb(buttons={StartZone.REGISTER: _("start.btn_register")})


def _menu_view(
    profile: UserProfile | None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if profile is not None and profile.status is UserProfileStatus.ACTIVE:
        return _("start.welcome"), _full_menu_kb(profile)
    if profile is not None and profile.status is UserProfileStatus.BANNED:
        return _("start.banned"), None
    text = _("start.on_moderation") if profile is not None else _("start.welcome")
    return text, _register_only_kb()


async def render_menu(
    *,
    target: Message | CallbackQuery,
    profile: UserProfile | None,
) -> None:
    text, kb = _menu_view(profile)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        return
    await target.answer(text, reply_markup=kb)


async def show_back_panel(*, callback: CallbackQuery, text: str) -> None:
    await callback.message.edit_text(
        text,
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()
