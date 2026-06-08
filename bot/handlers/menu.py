from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.i18n import I18n

from bot.forms.menu import open_menu
from bot.keyboards.menu import MENU_BUTTON_KEY
from common.models.user_profiles import UserProfile

router = Router(name="menu")


class MenuButtonFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.text is None:
            return False
        i18n = I18n.get_current(no_error=True)
        if i18n is None:
            return False
        return message.text in {
            i18n.gettext(MENU_BUTTON_KEY, locale=locale)
            for locale in i18n.available_locales
        }


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
