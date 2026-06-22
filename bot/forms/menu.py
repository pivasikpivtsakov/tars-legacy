from dataclasses import dataclass

from aiogram import Bot
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
from bot.utils.telegram import ignore_message_gone
from common.models.user_profiles import UserProfile, UserProfileStatus
from common.services.bot_switch import BotSwitchService

_MENU_MESSAGE_ID_KEY = "menu_message_id"


def menu_available(profile: UserProfile | None) -> bool:
    return profile is not None and profile.status is UserProfileStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class MenuContext:
    target: Message | CallbackQuery
    state: FSMContext
    profile: UserProfile | None
    for_admin: bool = False
    bot_enabled: bool = True
    is_moderator: bool = False


async def build_menu_context(
    *,
    target: Message | CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
    admin_ids: frozenset[int],
    moderator_ids: frozenset[int],
    bot_switch: BotSwitchService,
) -> MenuContext:
    user = target.from_user
    for_admin = user is not None and user.id in admin_ids
    return MenuContext(
        target=target,
        state=state,
        profile=profile,
        for_admin=for_admin,
        bot_enabled=await bot_switch.is_enabled() if for_admin else True,
        is_moderator=profile is not None and profile.id in moderator_ids,
    )


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
    with ignore_message_gone():
        await bot.delete_message(chat_id=chat_id, message_id=message_id)


def menu_inline_view(
    profile: UserProfile | None,
    *,
    for_admin: bool = False,
    bot_enabled: bool = True,
    is_moderator: bool = False,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if profile is not None and profile.status is UserProfileStatus.ACTIVE:
        markup = full_menu_kb(
            for_admin=for_admin,
            bot_enabled=bot_enabled,
            is_moderator=is_moderator,
        )
        if markup is None:
            return _("start.no_menu_actions"), None
        return _("start.welcome"), markup
    if profile is not None and profile.status is UserProfileStatus.BANNED:
        return _("start.banned"), None
    if profile is not None:
        return _("start.on_moderation"), None
    return _("start.welcome"), None


async def render_menu(context: MenuContext) -> None:
    target = context.target
    state = context.state
    profile = context.profile
    text, markup = menu_inline_view(
        profile,
        for_admin=context.for_admin,
        bot_enabled=context.bot_enabled,
        is_moderator=context.is_moderator,
    )
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
        with ignore_message_gone():
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
        reply_markup=menu_button_markup(profile=profile),
    )
    text, markup = menu_inline_view(profile)
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    await _remember_menu_message(state=state, message_id=sent.message_id)


async def show_panel(
    *,
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup,
) -> None:
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def show_back_panel(*, callback: CallbackQuery, text: str) -> None:
    await show_panel(
        callback=callback,
        text=text,
        markup=back_kb(back_text=_("start.btn_back")),
    )


async def install_menu_button(
    *,
    message: Message,
    profile: UserProfile,
    is_moderator: bool,
) -> None:
    await message.answer(
        _("start.menu_hint"),
        reply_markup=menu_button_markup(profile=profile, is_moderator=is_moderator),
    )


async def send_online_state(*, message: Message, profile: UserProfile) -> None:
    text = _("start.online_now_on") if profile.is_online else _("start.online_now_off")
    await message.answer(text, reply_markup=menu_button_markup(profile=profile))


async def open_menu(context: MenuContext) -> None:
    target = context.target
    if isinstance(target, Message):
        await _delete_remembered_menu(
            bot=target.bot,
            chat_id=target.chat.id,
            state=context.state,
        )
    await context.state.clear()
    await render_menu(context)
