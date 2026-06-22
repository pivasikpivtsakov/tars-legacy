from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.start import BackCB
from common.keyboards.packages import package_toggle_rows


class PackLimitEditCB(CallbackData, prefix="plim_edit"):
    size: int


class PackLimitResetCB(CallbackData, prefix="plim_reset"):
    pass


class PackLimitCancelCB(CallbackData, prefix="plim_cancel"):
    pass


def pack_limits_kb(*, reset_text: str, back_text: str) -> InlineKeyboardMarkup:
    rows = package_toggle_rows(
        selected=(),
        callback_factory=lambda size: PackLimitEditCB(size=size).pack(),
    )
    rows.append(
        [InlineKeyboardButton(text=reset_text, callback_data=PackLimitResetCB().pack())],
    )
    rows.append(
        [InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pack_limit_prompt_kb(*, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cancel_text, callback_data=PackLimitCancelCB().pack())],
        ],
    )
