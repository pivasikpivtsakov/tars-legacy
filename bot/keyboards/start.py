from collections.abc import Mapping
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class StartZone(StrEnum):
    ONLINE = "online"
    BALANCE = "balance"
    WITHDRAW = "withdraw"
    PACKS = "packs"
    PRIORITY = "priority"
    REGISTER = "register"


class OpenZoneCB(CallbackData, prefix="zone"):
    value: StartZone


class BackCB(CallbackData, prefix="back"):
    pass


def welcome_kb(*, buttons: Mapping[StartZone, str]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=text,
                callback_data=OpenZoneCB(value=zone).pack(),
            ),
        ]
        for zone, text in buttons.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb(*, back_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=back_text,
                    callback_data=BackCB().pack(),
                ),
            ],
        ],
    )
