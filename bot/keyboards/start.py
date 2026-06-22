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
    BALANCE = "balance"
    WITHDRAW = "withdraw"
    PRIORITY = "priority"
    REGISTER = "register"
    # for admins only
    TOGGLE_BOT_ENABLED = "toggle_bot_enabled"
    # for admins & moderators
    PACK_PRICE_LIMITS = "pack_price_limits"


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


def balance_kb(*, withdraw_text: str, back_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=withdraw_text,
                    callback_data=OpenZoneCB(value=StartZone.WITHDRAW).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=back_text,
                    callback_data=BackCB().pack(),
                ),
            ],
        ],
    )


def reply_menu_kb(*, menu_text: str, online_text: str | None = None) -> ReplyKeyboardMarkup:
    keyboard = []
    if online_text is not None:
        keyboard.append([KeyboardButton(text=online_text)])
    keyboard.append([KeyboardButton(text=menu_text)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
