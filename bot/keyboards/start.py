from collections.abc import Mapping
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


class StartZone(StrEnum):
    # for everyone
    ONLINE = "online"
    BALANCE = "balance"
    WITHDRAW = "withdraw"
    PRIORITY = "priority"
    REGISTER = "register"
    # for admins only
    TOGGLE_BOT_ENABLED = "toggle_bot_enabled"


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


def reply_menu_kb(*, menu_text: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=menu_text)]],
        resize_keyboard=True,
        is_persistent=True,
    )
