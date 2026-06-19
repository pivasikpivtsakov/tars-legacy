from collections.abc import Callable, Iterable

from aiogram.types import InlineKeyboardButton

from common.catalog.packages import PACKAGE_SIZES

CHECK_MARK = "\u2713"


def package_toggle_rows(
    *,
    selected: Iterable[int],
    callback_factory: Callable[[int], str],
    per_row: int = 3,
) -> list[list[InlineKeyboardButton]]:
    selected_set = set(selected)
    rows: list[list[InlineKeyboardButton]] = []
    for chunk_start in range(0, len(PACKAGE_SIZES), per_row):
        row = [
            InlineKeyboardButton(
                text=f"{CHECK_MARK} {size}" if size in selected_set else str(size),
                callback_data=callback_factory(size),
            )
            for size in PACKAGE_SIZES[chunk_start : chunk_start + per_row]
        ]
        rows.append(row)
    return rows
