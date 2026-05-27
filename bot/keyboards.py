from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

PACKAGE_SIZES: tuple[int, ...] = (60, 325, 660, 1800, 3850, 8100)


class WorksAloneCB(CallbackData, prefix="wa"):
    value: bool


class PackageToggleCB(CallbackData, prefix="pkg"):
    value: int


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


def packages_kb(*, selected: set[int], done_text: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chunk_start in range(0, len(PACKAGE_SIZES), 3):
        row = [
            InlineKeyboardButton(
                text=f"\u2713 {size}" if size in selected else str(size),
                callback_data=PackageToggleCB(value=size).pack(),
            )
            for size in PACKAGE_SIZES[chunk_start : chunk_start + 3]
        ]
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=done_text,
                callback_data=PackagesDoneCB().pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
