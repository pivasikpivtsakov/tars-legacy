from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards._packages import package_rows
from bot.keyboards.start import BackCB


def packages_editor_kb(
    *,
    selected: Iterable[int],
    back_text: str,
) -> InlineKeyboardMarkup:
    rows = package_rows(selected)
    rows.append(
        [
            InlineKeyboardButton(
                text=back_text,
                callback_data=BackCB().pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
