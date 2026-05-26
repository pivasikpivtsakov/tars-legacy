from aiogram import Router
from aiogram.types import Message
from aiogram.utils.i18n import gettext as _

router = Router(name="fallback")


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(_("unknown"))
