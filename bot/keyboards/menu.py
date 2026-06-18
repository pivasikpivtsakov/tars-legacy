from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import StartZone, reply_menu_kb, welcome_kb
from common.models.user_profiles import UserProfile

MENU_BUTTON_KEY = "start.btn_menu"


def _toggle_bot_text(*, bot_enabled: bool) -> str:
    return (
        _("start.btn_toggle_bot_disabled")
        if bot_enabled
        else _("start.btn_toggle_bot_enabled")
    )


def full_menu_kb(
    *,
    profile: UserProfile,
    for_admin: bool,
    bot_enabled: bool,
    is_moderator: bool = False,
) -> InlineKeyboardMarkup | None:
    buttons: dict[StartZone, str] = {}
    if not is_moderator:
        online_text = (
            _("start.btn_online_off") if profile.is_online else _("start.btn_online_on")
        )
        buttons = {
            StartZone.ONLINE: online_text,
            StartZone.BALANCE: _("start.btn_balance"),
            StartZone.WITHDRAW: _("start.btn_withdraw"),
            StartZone.PRIORITY: _("start.btn_priority"),
            StartZone.REGISTER: _("start.btn_register"),
        }
    if for_admin:
        buttons[StartZone.TOGGLE_BOT_ENABLED] = _toggle_bot_text(bot_enabled=bot_enabled)
    if not buttons:
        return None
    return welcome_kb(buttons=buttons)


def menu_button_markup() -> ReplyKeyboardMarkup:
    return reply_menu_kb(menu_text=_(MENU_BUTTON_KEY))
