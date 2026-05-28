from collections.abc import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton

from common.packages import PACKAGE_SIZES


class PackageToggleCB(CallbackData, prefix="pkg"):
    value: int


def package_rows(selected: Iterable[int]) -> list[list[InlineKeyboardButton]]:
    selected_set = set(selected)
    rows: list[list[InlineKeyboardButton]] = []
    for chunk_start in range(0, len(PACKAGE_SIZES), 3):
        row = [
            InlineKeyboardButton(
                text=f"\u2713 {size}" if size in selected_set else str(size),
                callback_data=PackageToggleCB(value=size).pack(),
            )
            for size in PACKAGE_SIZES[chunk_start : chunk_start + 3]
        ]
        rows.append(row)
    return rows
