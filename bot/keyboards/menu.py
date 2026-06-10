from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import StartZone, reply_menu_kb, welcome_kb
from common.models.user_profiles import UserProfile

MENU_BUTTON_KEY = "start.btn_menu"


def full_menu_kb(*, profile: UserProfile, for_admin: bool = False) -> InlineKeyboardMarkup:
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
        buttons[StartZone.TOGGLE_BOT_ENABLED] = _("start.btn_toggle_bot_enabled")
    return welcome_kb(buttons=buttons)


def menu_button_markup() -> ReplyKeyboardMarkup:
    return reply_menu_kb(menu_text=_(MENU_BUTTON_KEY))
