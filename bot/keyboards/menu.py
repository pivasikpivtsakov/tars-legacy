from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import OnlineButton, StartZone, reply_menu_kb, welcome_kb
from common.models.user_profiles import UserProfile

MENU_BUTTON_KEY = "start.btn_menu"
ONLINE_STATE_ON_KEY = "start.btn_online_state_on"
ONLINE_STATE_OFF_KEY = "start.btn_online_state_off"
ONLINE_STYLE_GREEN = "success"


def reply_text_matches(text: str, *keys: str) -> bool:
    i18n = I18n.get_current(no_error=True)
    if i18n is None:
        return False
    return text in {
        i18n.gettext(key, locale=locale) for key in keys for locale in i18n.available_locales
    }


def online_toggle_text(*, is_online: bool) -> str:
    return _(ONLINE_STATE_ON_KEY) if is_online else _(ONLINE_STATE_OFF_KEY)


def _toggle_bot_text(*, bot_enabled: bool) -> str:
    return _("start.btn_toggle_bot_disabled") if bot_enabled else _("start.btn_toggle_bot_enabled")


def full_menu_kb(
    *,
    for_admin: bool,
    bot_enabled: bool,
    is_moderator: bool = False,
) -> InlineKeyboardMarkup | None:
    buttons: dict[StartZone, str] = {}
    if not is_moderator:
        buttons = {
            StartZone.BALANCE: _("start.btn_balance"),
            StartZone.PRIORITY: _("start.btn_priority"),
            StartZone.REGISTER: _("start.btn_register"),
        }
    if for_admin or is_moderator:
        buttons[StartZone.PACK_PRICE_LIMITS] = _("start.btn_pack_price_limits")
        buttons[StartZone.CODE_ORDER_PRICE] = _("start.btn_code_order_price")
    if for_admin:
        buttons[StartZone.TOGGLE_BOT_ENABLED] = _toggle_bot_text(bot_enabled=bot_enabled)
    if not buttons:
        return None
    return welcome_kb(buttons=buttons)


def menu_button_markup(
    *,
    profile: UserProfile | None = None,
    is_moderator: bool = False,
) -> ReplyKeyboardMarkup:
    online_button = None
    if profile is not None and not is_moderator:
        online_button = OnlineButton(
            text=online_toggle_text(is_online=profile.is_online),
            style=ONLINE_STYLE_GREEN if profile.is_online else None,
        )
    return reply_menu_kb(menu_text=_(MENU_BUTTON_KEY), online_button=online_button)
