from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class StartZone(StrEnum):
    ONLINE = "online"
    WITHDRAW = "withdraw"
    PACKS = "packs"
    PRIORITY = "priority"
    REGISTER = "register"


class OpenZoneCB(CallbackData, prefix="zone"):
    value: StartZone


class BackCB(CallbackData, prefix="back"):
    pass


def welcome_kb(
    *,
    online_text: str,
    withdraw_text: str,
    packs_text: str,
    priority_text: str,
    register_text: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=online_text,
                callback_data=OpenZoneCB(value=StartZone.ONLINE).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=withdraw_text,
                callback_data=OpenZoneCB(value=StartZone.WITHDRAW).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=packs_text,
                callback_data=OpenZoneCB(value=StartZone.PACKS).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=priority_text,
                callback_data=OpenZoneCB(value=StartZone.PRIORITY).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=register_text,
                callback_data=OpenZoneCB(value=StartZone.REGISTER).pack(),
            ),
        ],
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
