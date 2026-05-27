from collections.abc import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards._packages import package_rows
from bot.keyboards.start import BackCB


class PacksSaveCB(CallbackData, prefix="pkg_save"):
    pass


def packages_editor_kb(
    *,
    selected: Iterable[int],
    save_text: str,
    back_text: str,
) -> InlineKeyboardMarkup:
    rows = package_rows(selected)
    rows.append(
        [
            InlineKeyboardButton(
                text=save_text,
                callback_data=PacksSaveCB().pack(),
            ),
            InlineKeyboardButton(
                text=back_text,
                callback_data=BackCB().pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
