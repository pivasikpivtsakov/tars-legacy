from collections.abc import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards._packages import package_rows


class WorksAloneCB(CallbackData, prefix="wa"):
    value: bool


class PackagesDoneCB(CallbackData, prefix="pkg_done"):
    pass


def works_alone_kb(*, yes_text: str, no_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=yes_text,
                    callback_data=WorksAloneCB(value=True).pack(),
                ),
                InlineKeyboardButton(
                    text=no_text,
                    callback_data=WorksAloneCB(value=False).pack(),
                ),
            ],
        ],
    )


def packages_kb(*, selected: Iterable[int], done_text: str) -> InlineKeyboardMarkup:
    rows = package_rows(selected)
    rows.append(
        [
            InlineKeyboardButton(
                text=done_text,
                callback_data=PackagesDoneCB().pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
