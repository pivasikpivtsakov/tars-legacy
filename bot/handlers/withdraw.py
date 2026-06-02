from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import require_complete_profile, show_back_panel
from bot.keyboards.start import OpenZoneCB, StartZone
from common.models.user_profiles import UserProfile

router = Router(name="withdraw")


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.WITHDRAW))
async def open_withdraw(
    callback: CallbackQuery,
    profile: UserProfile | None,
) -> None:
    complete_profile = await require_complete_profile(callback=callback, profile=profile)
    if complete_profile is None:
        return
    await show_back_panel(callback=callback, text=_("withdraw.placeholder"))
