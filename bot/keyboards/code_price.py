from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.start import BackCB


class CodePriceEditCB(CallbackData, prefix="cprice_edit"):
    pass


class CodePriceCancelCB(CallbackData, prefix="cprice_cancel"):
    pass


def code_price_kb(*, edit_text: str, back_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=edit_text, callback_data=CodePriceEditCB().pack())],
            [InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())],
        ],
    )


def code_price_prompt_kb(*, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cancel_text, callback_data=CodePriceCancelCB().pack())],
        ],
    )
