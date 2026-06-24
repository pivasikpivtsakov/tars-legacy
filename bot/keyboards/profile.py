from collections.abc import Iterable, Mapping
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.start import BackCB
from common.keyboards.packages import package_toggle_rows


class PackTapCB(CallbackData, prefix="pkg_tap"):
    value: int


class PackCancelCB(CallbackData, prefix="pkg_cancel"):
    pass


class ChatAddableCB(CallbackData, prefix="ca"):
    value: bool


class WithCodesCB(CallbackData, prefix="wc"):
    value: bool


class PackagesDoneCB(CallbackData, prefix="pkg_done"):
    pass


class ProfileField(StrEnum):
    chat_addable = "chat_addable"
    with_codes = "with_codes"
    packages = "packages"
    withdrawal_method = "withdrawal_method"
    work_start = "work_start"
    work_end = "work_end"


class EditFieldCB(CallbackData, prefix="ef"):
    field: ProfileField


class EditSaveCB(CallbackData, prefix="ef_save"):
    pass


def _bool_kb(
    *,
    yes_text: str,
    no_text: str,
    yes_callback: str,
    no_callback: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes_text, callback_data=yes_callback),
                InlineKeyboardButton(text=no_text, callback_data=no_callback),
            ],
        ],
    )


def chat_addable_kb(*, yes_text: str, no_text: str) -> InlineKeyboardMarkup:
    return _bool_kb(
        yes_text=yes_text,
        no_text=no_text,
        yes_callback=ChatAddableCB(value=True).pack(),
        no_callback=ChatAddableCB(value=False).pack(),
    )


def with_codes_kb(*, yes_text: str, no_text: str) -> InlineKeyboardMarkup:
    return _bool_kb(
        yes_text=yes_text,
        no_text=no_text,
        yes_callback=WithCodesCB(value=True).pack(),
        no_callback=WithCodesCB(value=False).pack(),
    )


def packages_grid_kb(*, selected: Iterable[int], done_text: str) -> InlineKeyboardMarkup:
    rows = package_toggle_rows(
        selected=selected,
        callback_factory=lambda size: PackTapCB(value=size).pack(),
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=done_text,
                callback_data=PackagesDoneCB().pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pack_price_kb(*, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=cancel_text,
                    callback_data=PackCancelCB().pack(),
                ),
            ],
        ],
    )


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
