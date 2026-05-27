from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from bot.handlers.common import require_complete_profile
from bot.keyboards.start import OpenZoneCB, StartZone, back_kb
from bot.storage.user_profiles import UserProfileRepository

router = Router(name="withdraw")


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.WITHDRAW))
async def open_withdraw(
    callback: CallbackQuery,
    profiles: UserProfileRepository,
) -> None:
    if (await require_complete_profile(callback=callback, profiles=profiles)) is None:
        return
    await callback.message.edit_text(
        _("withdraw.placeholder"),
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()
