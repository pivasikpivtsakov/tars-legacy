from collections.abc import Iterable, Mapping
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.start import BackCB
from common.keyboards.packages import package_toggle_rows


class PackageToggleCB(CallbackData, prefix="pkg"):
    value: int


class WorksAloneCB(CallbackData, prefix="wa"):
    value: bool


class PackagesDoneCB(CallbackData, prefix="pkg_done"):
    pass


class ProfileField(StrEnum):
    works_alone = "works_alone"
    packages = "packages"
    price_60 = "price_60"
    withdrawal_method = "withdrawal_method"
    work_start = "work_start"
    work_end = "work_end"


class EditFieldCB(CallbackData, prefix="ef"):
    field: ProfileField


class EditSaveCB(CallbackData, prefix="ef_save"):
    pass


def package_rows(selected: Iterable[int]) -> list[list[InlineKeyboardButton]]:
    return package_toggle_rows(
        selected=selected,
        callback_factory=lambda size: PackageToggleCB(value=size).pack(),
    )


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


def edit_menu_kb(
    *,
    labels: Mapping[ProfileField, str],
    save_text: str,
    cancel_text: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=text,
                callback_data=EditFieldCB(field=field).pack(),
            ),
        ]
        for field, text in labels.items()
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=save_text,
                callback_data=EditSaveCB().pack(),
            ),
        ],
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=cancel_text,
                callback_data=BackCB().pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
