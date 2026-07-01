from collections.abc import Mapping
from dataclasses import dataclass
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
    HISTORY = "history"
    PRIORITY = "priority"
    REGISTER = "register"
    # for admins only
    TOGGLE_BOT_ENABLED = "toggle_bot_enabled"
    # for admins & moderators
    PACK_PRICE_LIMITS = "pack_price_limits"
    CODE_ORDER_PRICE = "code_order_price"


class OpenZoneCB(CallbackData, prefix="zone"):
    value: StartZone


class BackCB(CallbackData, prefix="back"):
    pass


class HistoryPageCB(CallbackData, prefix="hist"):
    offset: int


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


def balance_kb(*, withdraw_text: str, history_text: str, back_text: str) -> InlineKeyboardMarkup:
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
                    text=history_text,
                    callback_data=OpenZoneCB(value=StartZone.HISTORY).pack(),
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


def history_kb(
    *,
    offset: int,
    limit: int,
    has_next: bool,
    prev_text: str,
    next_text: str,
    back_text: str,
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                text=prev_text,
                callback_data=HistoryPageCB(offset=max(offset - limit, 0)).pack(),
            ),
        )
    if has_next:
        nav.append(
            InlineKeyboardButton(
                text=next_text,
                callback_data=HistoryPageCB(offset=offset + limit).pack(),
            ),
        )
    rows: list[list[InlineKeyboardButton]] = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=back_text, callback_data=BackCB().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dataclass(frozen=True, slots=True)
class OnlineButton:
    text: str
    style: str | None = None


def reply_menu_kb(
    *,
    menu_text: str,
    online_button: OnlineButton | None = None,
) -> ReplyKeyboardMarkup:
    keyboard = []
    if online_button is not None:
        keyboard.append([KeyboardButton(text=online_button.text, style=online_button.style)])
    keyboard.append([KeyboardButton(text=menu_text)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
