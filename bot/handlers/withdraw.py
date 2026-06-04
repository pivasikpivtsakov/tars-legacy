from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import show_back_panel
from bot.keyboards.start import OpenZoneCB, StartZone
from bot.middlewares.profile import require_active_profile

router = Router(name="withdraw")


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.WITHDRAW))
@require_active_profile
async def open_withdraw(callback: CallbackQuery) -> None:
    await show_back_panel(callback=callback, text=_("withdraw.placeholder"))
