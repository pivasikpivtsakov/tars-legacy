import contextlib

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n import gettext as _

from bot.keyboards.start import StartZone, back_kb, reply_menu_kb, welcome_kb
from common.models.user_profiles import UserProfile, UserProfileStatus

router = Router(name="menu")

_MENU_BUTTON_KEY = "start.btn_menu"
_MENU_MESSAGE_ID_KEY = "menu_message_id"


async def _remember_menu_message(*, state: FSMContext, message_id: int) -> None:
    await state.update_data({_MENU_MESSAGE_ID_KEY: message_id})


async def _delete_remembered_menu(
    *,
    bot: Bot,
    chat_id: int,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    message_id = data.get(_MENU_MESSAGE_ID_KEY)
    if message_id is None:
        return
    with contextlib.suppress(TelegramBadRequest):
        await bot.delete_message(chat_id=chat_id, message_id=message_id)


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
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    text, kb = _menu_view(profile)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await _remember_menu_message(
            state=state,
            message_id=target.message.message_id,
        )
        return
    sent = await target.answer(text, reply_markup=kb)
    await _remember_menu_message(state=state, message_id=sent.message_id)


async def send_menu(
    *,
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    text, kb = _menu_view(profile)
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
    await _remember_menu_message(state=state, message_id=sent.message_id)


async def show_back_panel(*, callback: CallbackQuery, text: str) -> None:
    await callback.message.edit_text(
        text,
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()


class MenuButtonFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.text is None:
            return False
        i18n = I18n.get_current(no_error=True)
        if i18n is None:
            return False
        return message.text in {
            i18n.gettext(_MENU_BUTTON_KEY, locale=locale)
            for locale in i18n.available_locales
        }


def menu_button_markup() -> ReplyKeyboardMarkup:
    return reply_menu_kb(menu_text=_(_MENU_BUTTON_KEY))


async def install_menu_button(*, message: Message) -> None:
    await message.answer(_("start.menu_hint"), reply_markup=menu_button_markup())


async def open_menu(
    *,
    target: Message | CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    if isinstance(target, Message):
        await _delete_remembered_menu(
            bot=target.bot,
            chat_id=target.chat.id,
            state=state,
        )
    await state.clear()
    await render_menu(target=target, state=state, profile=profile)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await open_menu(target=message, state=state, profile=profile)


@router.message(MenuButtonFilter())
async def on_menu_button(
    message: Message,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await open_menu(target=message, state=state, profile=profile)
