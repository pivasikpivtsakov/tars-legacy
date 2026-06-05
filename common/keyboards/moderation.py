from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class ModApproveCB(CallbackData, prefix="mod_ok"):
    profile_id: int


class ModDenyCB(CallbackData, prefix="mod_no"):
    profile_id: int


def moderation_decision_kb(
    *,
    profile_id: int,
    yes_text: str,
    no_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=yes_text,
                    callback_data=ModApproveCB(profile_id=profile_id).pack(),
                ),
                InlineKeyboardButton(
                    text=no_text,
                    callback_data=ModDenyCB(profile_id=profile_id).pack(),
                ),
            ],
        ],
    )
