import contextlib

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.i18n import gettext as _

from bot.keyboards.menu import full_menu_kb, menu_button_markup
from bot.keyboards.start import back_kb
from common.models.user_profiles import UserProfile, UserProfileStatus

_MENU_MESSAGE_ID_KEY = "menu_message_id"


def menu_available(profile: UserProfile | None) -> bool:
    return profile is not None and profile.status is UserProfileStatus.ACTIVE


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


def menu_inline_view(
    profile: UserProfile | None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if profile is not None and profile.status is UserProfileStatus.ACTIVE:
        return _("start.welcome"), full_menu_kb(profile)
    if profile is not None and profile.status is UserProfileStatus.BANNED:
        return _("start.banned"), None
    if profile is not None:
        return _("start.on_moderation"), None
    return _("start.welcome"), None


async def render_menu(
    *,
    target: Message | CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    text, markup = menu_inline_view(profile)
    if menu_available(profile):
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup)
            await _remember_menu_message(
                state=state,
                message_id=target.message.message_id,
            )
            return
        sent = await target.answer(text, reply_markup=markup)
        await _remember_menu_message(state=state, message_id=sent.message_id)
        return
    message = target.message if isinstance(target, CallbackQuery) else target
    if isinstance(target, CallbackQuery):
        with contextlib.suppress(TelegramBadRequest):
            await target.message.delete()
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


async def send_menu(
    *,
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await bot.send_message(
        chat_id=chat_id,
        text=_("start.menu_hint"),
        reply_markup=menu_button_markup(),
    )
    text, markup = menu_inline_view(profile)
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    await _remember_menu_message(state=state, message_id=sent.message_id)


async def show_back_panel(*, callback: CallbackQuery, text: str) -> None:
    await callback.message.edit_text(
        text,
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()


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
